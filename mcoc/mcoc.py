import re
from datetime import datetime, timedelta
from dateutil.parser import parse as dateParse
from collections import UserDict, defaultdict, ChainMap  #, namedtuple, OrderedDict
from functools import partial
from math import *
from operator import attrgetter
import os
import time
import inspect
import aiohttp
import logging
import csv
import json
import pygsheets
import random

import asyncio
from .utils.dataIO import dataIO
from functools import wraps
import discord
from discord.ext import commands
from .utils import chat_formatting as chat
from __main__ import send_cmd_help
from cogs.utils import checks

## experimental jjw
# import matplotlib.pyplot as plt

logger = logging.getLogger('red.mcoc')
logger.setLevel(logging.INFO)

class SignatureError(Exception):
    pass

class MissingKabamText(SignatureError):
    pass

class MissingSignatureData(SignatureError):
    pass

class SignatureSchemaError(SignatureError):
    pass

class InsufficientData(SignatureError):
    pass

class LowDataWarning(SignatureError):
    pass

class PoorDataFit(SignatureError):
    pass

class TitleError(Exception):
    def __init__(self, champ):
        self.champ = champ

data_files = {
    'spotlight': {'remote': 'https://docs.google.com/spreadsheets/d/1I3T2G2tRV05vQKpBfmI04VpvP5LjCBPfVICDmuJsjks/pub?gid=0&single=true&output=csv',
                'local': 'data/mcoc/spotlight_data.csv', 'update_delta': 1},
    'crossreference': {'remote': 'https://docs.google.com/spreadsheets/d/1WghdD4mfchduobH0me4T6IvhZ-owesCIyLxb019744Y/pub?gid=0&single=true&output=csv',
                'local': 'data/mcoc/crossreference.csv', 'update_delta': 1},
    'prestigeCSV':{'remote': 'https://docs.google.com/spreadsheets/d/1I3T2G2tRV05vQKpBfmI04VpvP5LjCBPfVICDmuJsjks/pub?gid=1346864636&single=true&output=csv',
                'local': 'data/mcoc/prestige.csv', 'update_delta': 1},
    'duelist' : {'remote': 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTsPSNaY6WbNF1fY49jqjRm9hJZ60Sa6fU6Yd_t7nOrIxikVj-Y7JW_YSPwHoJfix9MA4YgWSenIwfl/pub?gid=694495962&single=true&output=csv',
                'local': 'data/mcoc/duelist.csv', 'update_delta': 1},
    #'masteries' : {'remote':'https://docs.google.com/spreadsheets/d/1mEnMrBI5c8Tbszr0Zne6qHkW6WxZMXBOuZGe9XmrZm8/pub?gid=0&single=true&output=csv',
                #'local': 'data/mcoc/masteries.csv', 'update_delta': 1},
    }

PATREON = 'https://patreon.com/collectorbot'
GS_BASE='https://sheets.googleapis.com/v4/spreadsheets/{}/values/{}?key=AIzaSyBugcjKbOABZEn-tBOxkj0O7j5WGyz80uA&majorDimension=ROWS'
GSHEET_ICON='https://d2jixqqjqj5d23.cloudfront.net/assets/developer/imgs/icons/google-spreadsheet-icon.png'
AUNTMAI = 'https://raw.githubusercontent.com/CollectorDevTeam/assets/master/data/images/AuntMai_Tile_Center.png'
SPOTLIGHT_DATASET='https://docs.google.com/spreadsheets/d/e/2PACX-1vRFLWYdFMyffeOzKiaeQeqoUgaESknK-QpXTYV2GdJgbxQkeCjoSajuLjafKdJ5imE1ADPYeoh8QkAr/pubhtml?gid=1483787822&single=true'
SPOTLIGHT_SURVEY='https://docs.google.com/forms/d/e/1FAIpQLSe4JYzU5CsDz2t0gtQ4QKV8IdVjE5vaxJBrp-mdfKxOG8fYiA/viewform?usp=sf_link'
PRESTIGE_SURVEY='https://docs.google.com/forms/d/e/1FAIpQLSeo3YhZ70PQ4t_I4i14jX292CfBM8DMb5Kn2API7O8NAsVpRw/viewform?usp=sf_link'
MODOKSAYS = ['alien', 'buffoon', 'charlatan', 'creature', 'die', 'disintegrate',
        'evaporate', 'feelmypower', 'fool', 'fry', 'haha', 'iamscience', 'idiot',
        'kill', 'oaf', 'peabrain', 'pretender', 'sciencerules', 'silence',
        'simpleton', 'tincan', 'tremble', 'ugh', 'useless']

local_files = {
    "sig_coeff": "data/mcoc/sig_coeff.csv",
    "effect_keys": "data/mcoc/effect_keys.csv",
    "signature": "data/mcoc/signature.json",
    "sig_coeff_4star": "data/mcoc/sig_coeff_4star.json",
    "sig_coeff_5star": "data/mcoc/sig_coeff_5star.json",
    "synergy": "data/mcoc/synergy.json",
}

async def postprocess_sig_data(bot, struct):
    sgd = cogs.mcocTools.StaticGameData()
    sigs = sgd.cdt_data
    # sigs = load_kabam_json(kabam_bcg_stat_en, aux=struct.get("bcg_stat_en_aux"))
    mcoc = bot.get_cog('MCOC')
    missing = []
    aux = {i['k']: i['v'] for i in struct.get("bcg_stat_en_aux", [])}
    for key in struct.keys():
        champ_class = mcoc.champions.get(key.lower(), None)
        if champ_class is None:
            continue
        try:
            struct[key]['kabam_text'] = champ_class.get_kabam_sig_text(
                    champ_class, sigs=sigs,
                    # champ_exceptions=struct['kabam_key_override'])
                    champ_exceptions=aux)
        except TitleError as e:
            missing.append(e.champ)
    if missing:
        await bot.say("Skipped Champs due to Kabam Key Errors: {}".format(', '.join(missing)))

# gsheet_files = {
#     'signature': {'gkey': '1kNvLfeWSCim8liXn6t0ksMAy5ArZL5Pzx4hhmLqjukg',
#             'local': local_files['signature'],
#             'postprocess': postprocess_sig_data,
#             },
#     'sig_coeff_4star': {'gkey': '1WrAj9c41C4amzP8-jY-QhyKurO8mIeclk9C1pSvmWsk',
#             'local': local_files['sig_coeff_4star'],
#             },
#     'sig_coeff_5star': {'gkey': '1VHi9MioEGAsLoZneYQm37gPkmbD8mx7HHa-zuMiwWns',
#             'local': local_files['sig_coeff_5star'],
#             },
#     'synergy': {'gkey': '1Apun0aUcr8HcrGmIODGJYhr-ZXBCE_lAR7EaFg_ZJDY',
#             'local': local_files['synergy'],
#             },
# }

star_glyph = "★"
lolmap_path="data/mcoc/maps/lolmap.png"
file_checks_json = "data/mcoc/file_checks.json"
remote_data_basepath = "https://raw.githubusercontent.com/CollectorDevTeam/assets/master/data/"
icon_sdf = "https://raw.githubusercontent.com/CollectorDevTeam/assets/master/data/sdf_icon.png"

ability_desc = "data/mcoc/ability-desc/{}.txt"

class_color_codes = {
        'Cosmic': discord.Color(0x2799f7), 'Tech': discord.Color(0x0033ff),
        'Mutant': discord.Color(0xffd400), 'Skill': discord.Color(0xdb1200),
        'Science': discord.Color(0x0b8c13), 'Mystic': discord.Color(0x7f0da8),
        'All': discord.Color(0x03f193), 'Superior': discord.Color(0x03f193), 'default': discord.Color.light_grey(),
        }

class_emoji = {
        'Superior':'<:all2:339511715920084993>',
        'All':'<:all2:339511715920084993>',
        'Cosmic':'<:cosmic2:339511716104896512>',
        'Tech':'<:tech2:339511716197171200>',
        'Mutant':'<:mutant2:339511716201365514>',
        'Skill':'<:skill2:339511716549230592>',
        'Science':'<:science2:339511716029267969>',
        'Mystic':'<:mystic2:339511716150771712>',
        'default': '',
        }

def from_flat(flat, ch_rating):
    denom = 5 * ch_rating + 1500 + flat
    return round(100*flat/denom, 2)

def to_flat(per, ch_rating):
    num = (5 * ch_rating + 1500) * per
    return round(num/(100-per), 2)

class QuietUserError(commands.UserInputError):
    pass

class AmbiguousArgError(QuietUserError):
    pass

class MODOKError(QuietUserError):
    pass

class ChampConverter(commands.Converter):
    '''Argument Parsing class that geneartes Champion objects from user input'''

    arg_help = '''
    Specify a single champion with optional parameters of star, rank, or sig.
    Champion names can be a number of aliases or partial aliases if no conflicts are found.

    The optional arguments can be in any order, with or without spaces.
        <digit>* specifies star <default: 4>
        r<digit> specifies rank <default: 5>
        s<digit> specifies signature level <default: 99>

    Examples:
        4* yj r4 s30  ->  4 star Yellowjacket rank 4/40 sig 30
        r35*im        ->  5 star Ironman rank 3/45 sig 99
        '''
#(?:(?:s(?P<sig>[0-9]{1,3})) |(?:r(?P<rank>[1-5]))|(?:(?P<star>[1-5])\\?\*)|(?:d(?P<debug>[0-9]{1,2})))(?=\b|[a-zA-Z]|(?:[1-5]\\?\*))
    _bare_arg = None
    parse_re = re.compile(r'''(?:s(?P<sig>[0-9]{1,3}))
                             |(?:r(?P<rank>[1-5]))
                             |(?:(?P<star>[1-6])(?:★|☆|\\?\*))
                             |(?:d(?P<debug>[0-9]{1,2}))''', re.X)
    async def convert(self):
        bot = self.ctx.bot
        attrs = {}
        if self._bare_arg:
            args = self.argument.rsplit(' ', maxsplit=1)
            if len(args) > 1 and args[-1].isdecimal():
                attrs[self._bare_arg] = int(args[-1])
                self.argument = args[0]
        arg = ''.join(self.argument.lower().split(' '))
        arg = arg.replace('(','').replace(')','').replace('-','')
        for m in self.parse_re.finditer(arg):
            attrs[m.lastgroup] = int(m.group(m.lastgroup))
        token = self.parse_re.sub('', arg)
        if not token:
            err_str = "No Champion remains from arg '{}'".format(self.argument)
            #await bot.say(err_str)
            #raise commands.BadArgument(err_str)
            raise MODOKError(err_str)
        return (await self.get_champion(bot, token, attrs))

    async def get_champion(self, bot, token, attrs):
        mcoc = bot.get_cog('MCOC')
        try:
            champ = await mcoc.get_champion(token, attrs)
        except KeyError:
            champs = await mcoc.search_champions('.*{}.*'.format(token), attrs)
            if len(champs) == 1:
                await bot.say("'{}' was not exact but found close alternative".format(
                        token))
                champ = champs[0]
            elif len(champs) > 1:
                em = discord.Embed(title='Ambiguous Argument "{}"'.format(token),
                        description='Resolved to multiple possible champs')
                for champ in champs:
                    em.add_field(name=champ.full_name, inline=False,
                            value=chat.box(', '.join(champ.alias_set)))
                await bot.say(embed=em)
                raise AmbiguousArgError('Multiple matches for arg "{}"'.format(token))
            else:
                err_str = "Cannot resolve alias for '{}'".format(token)
                #await bot.say(err_str)
                #raise commands.BadArgument(err_str)
                raise MODOKError(err_str)
        return champ

class ChampConverterSig(ChampConverter):
    _bare_arg = 'sig'
    arg_help = ChampConverter.arg_help + '''
    Bare Number argument for this function is sig level:
        "yjr5s30" is equivalent to "yjr5 30"'''

class ChampConverterRank(ChampConverter):
    _bare_arg = 'rank'
    arg_help = ChampConverter.arg_help + '''
    Bare Number argument for this function is rank:
        "yjr5s30" is equivalent to "yjs30 5"'''

class ChampConverterStar(ChampConverter):
    _bare_arg = 'star'
    arg_help = ChampConverter.arg_help + '''
    Bare Number argument for this function is star:
        "5*yjr5s30" is equivalent to "yjr5s30 5"'''

class ChampConverterDebug(ChampConverter):
    _bare_arg = 'debug'

class ChampConverterMult(ChampConverter):

    arg_help = '''
    Specify multiple champions with optional parameters of star, rank, or sig.
    Champion names can be a number of aliases or partial aliases if no conflicts are found.

    The optional arguments can be in any order.
        <digit>* specifies star <default: 4>
        r<digit> specifies rank <default: 5>
        s<digit> specifies signature level <default: 99>

    If optional arguments are listed without a champion, it changes the default for all
    remaining champions.  Arguments attached to a champion are local to that champion
    only.

    Examples:
        s20 yj im        ->  4* Yellowjacket r5/50 sig 20, 4* Ironman r5/50 sig 20
        r35*ims20 ims40  ->  5 star Ironman r3/45 sig 20, 4* Ironman r5/50 sig 40
        r4s20 yj ims40 lc -> 4* Yellowjacket r4/40 sig 20, 4* Ironman r4/40 sig 40, 4* Luke Cage r4/40 sig 20
        '''

    async def convert(self):
        bot = self.ctx.bot
        champs = []
        default = {}
        dangling_arg = None
        for arg in self.argument.lower().split(' '):
            attrs = default.copy()
            for m in self.parse_re.finditer(arg):
                attrs[m.lastgroup] = int(m.group(m.lastgroup))
            token = self.parse_re.sub('', arg)
            if token != '':
                champ = await self.get_champion(bot, token, attrs)
                dangling_arg = None
                champs.append(champ)
            else:
                default.update(attrs)
                dangling_arg = arg
        if dangling_arg:
            em = discord.Embed(title='Dangling Argument',
                    description="Last argument '{}' is unused.\n".format(dangling_arg)
                        + "Place **before** the champion or **without a space**.")
            await bot.say(embed=em)
        return champs

async def warn_bold_say(bot, msg):
    await bot.say('\u26a0 ' + chat.bold(msg))


# moved a bunch of definitions to mcocTools

# def numericise_bool(val):
#     if val == "TRUE":
#         return True
#     elif val == "FALSE":
#         return False
#     else:
#         return numericise(val)
#
# def strip_and_numericise(val):
#         return numericise_bool(val.strip())

# def cell_to_list(cell):
#     if cell is not None:
#         return [strip_and_numericise(i) for c in cell.split(',') for i in c.split('\n')]
#
# def cell_to_dict(cell):
#     if cell is None:
#         return None
#     ret  = {}
#     for i in cell.split(','):
#         k, v = [strip_and_numericise(j) for j in i.split(':')]
#         ret[k] = v
#     return ret

# def remove_commas(cell):
#     return numericise_bool(cell.replace(',', ''))
#
# def remove_NA(cell):
#     return None if cell in ("#N/A", "") else numericise_bool(cell)

class AliasDict(UserDict):
    '''Custom dictionary that uses a tuple of aliases as key elements.
    Item addressing is handled either from the tuple as a whole or any
    element within the tuple key.
    '''
    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        for k in self.data.keys():
            if key in k:
                return self.data[k]
        raise KeyError("Invalid Key '{}'".format(key))

class ChampionFactory():
    '''Creation and storage of the dynamically created Champion subclasses.
    A new subclass is created for every champion defined.  Then objects are
    created from user function calls off of the dynamic classes.'''

    def __init__(self, *args, **kwargs):
        self.cooldown_delta = 5 * 60
        self.cooldown = time.time() - self.cooldown_delta - 1
        self.needs_init = True
        super().__init__(*args, **kwargs)
        self.bot.loop.create_task(self.update_local())  # async init
        logger.debug('ChampionFactory Init')

    def data_struct_init(self):
        logger.info('Preparing data structures')
        self._prepare_aliases()
        self._prepare_prestige_data()
        self.needs_init = False

    async def update_local(self):
        now = time.time()
        if now - self.cooldown_delta < self.cooldown:
            return
        self.cooldown = now
        is_updated = await self.verify_cache_remote_files()
        if is_updated or self.needs_init:
            self.data_struct_init()

    def create_champion_class(self, bot, alias_set, **kwargs):
        if not kwargs['champ'.strip()]: #empty line
            return
        kwargs['bot'] = bot
        kwargs['alias_set'] = alias_set
        kwargs['klass'] = kwargs.pop('class', 'default')
        if kwargs['klass'] == '':
            kwargs['klass'] = 'default'  # protect against malformed 'class' attr

        if not kwargs['champ'].strip():  #empty line
            return
        kwargs['full_name'] = kwargs['champ']
        kwargs['bold_name'] = chat.bold(' '.join(
                [word.capitalize() for word in kwargs['full_name'].split(' ')]))
        kwargs['class_color'] = CDT_COLORS[kwargs['klass']]
        kwargs['class_icon'] = class_emoji[kwargs['klass']]

        kwargs['class_tags'] = {'#' + kwargs['klass'].lower()}
        for a in kwargs['abilities'].split(','):
            kwargs['class_tags'].add('#' + ''.join(a.lower().split(' ')))
        for a in kwargs['hashtags'].split('#'):
            newtag = '#' + ''.join(a.lower().split(' '))
            kwargs['class_tags'].add(newtag)
            if ':' in newtag and not newtag.startswith('#size'):
                kwargs['class_tags'].add(newtag.split(':')[0])
        for a in kwargs['extended_abilities'].split(','):
            kwargs['class_tags'].add('#' + ''.join(a.lower().split(' ')))
        for a in kwargs['counters'].split(','):
            kwargs['class_tags'].add('#!' + ''.join(a.lower().split(' ')))
        if kwargs['class_tags']:
            kwargs['class_tags'].difference_update({'#', '#!'})

        for key, value in kwargs.items():
            if not value or value == 'n/a':
                kwargs[key] = None

        champion = type(kwargs['mattkraftid'], (Champion,), kwargs)
        self.champions[tuple(alias_set)] = champion
        logger.debug('Creating Champion class {}'.format(kwargs['mattkraftid']))
        return champion

    async def get_champion(self, name_id, attrs=None):
        '''straight alias lookup followed by new champion object creation'''
        #await self.update_local()
        return self.champions[name_id](attrs)

    async def search_champions(self, search_str, attrs=None):
        '''searching through champion aliases and allowing partial matches.
        Returns an array of new champion objects'''
        #await self.update_local()
        re_str = re.compile(search_str)
        champs = []
        for champ in self.champions.values():
            if any([re_str.search(alias) is not None
                    for alias in champ.alias_set]):
                champs.append(champ(attrs))
        return champs

    async def verify_cache_remote_files(self, verbose=False, force_cache=False):
        logger.info('Check remote files')
        if os.path.exists(file_checks_json):
            try:
                file_checks = dataIO.load_json(file_checks_json)
            except:
                file_checks = {}
        else:
            file_checks = {}
        async with aiohttp.ClientSession() as s:
            is_updated = False
            for key in data_files.keys():
                if key in file_checks:
                    last_check = datetime(*file_checks.get(key))
                else:
                    last_check = None
                remote_check = await self.cache_remote_file(key, s, verbose=verbose,
                        last_check=last_check)
                if remote_check:
                    is_updated = True
                    file_checks[key] = remote_check.timetuple()[:6]
        dataIO.save_json(file_checks_json, file_checks)
        return is_updated

    async def cache_remote_file(self, key, session, verbose=False, last_check=None,
                force_cache=False):
        dargs = data_files[key]
        strf_remote = '%a, %d %b %Y %H:%M:%S %Z'
        response = None
        remote_check = False
        now = datetime.now()
        if os.path.exists(dargs['local']) and not force_cache:
            if last_check:
                check_marker = now - timedelta(days=dargs['update_delta'])
                refresh_remote_check = check_marker > last_check
            else:
                refresh_remote_check = True
            local_dt = datetime.fromtimestamp(os.path.getmtime(dargs['local']))
            if refresh_remote_check:
                response = await session.get(dargs['remote'])
                if 'Last-Modified' in response.headers:
                    remote_dt = datetime.strptime(response.headers['Last-Modified'], strf_remote)
                    remote_check = now
                    if remote_dt < local_dt:
                        # Remote file is older, so no need to transfer
                        response = None
        else:
            response = await session.get(dargs['remote'])
        if response and response.status == 200:
            logger.info('Caching ' + dargs['local'])
            with open(dargs['local'], 'wb') as fp:
                fp.write(await response.read())
            remote_check = now
            await response.release()
        elif response:
            err_str = "HTTP error code {} while trying to Collect {}".format(
                    response.status, key)
            logger.error(err_str)
            await response.release()
        elif verbose and remote_check:
            logger.info('Local file up-to-date:', dargs['local'], now)
        return remote_check

    def _prepare_aliases(self):
        '''Create a python friendly data structure from the aliases json'''
        logger.debug('Preparing aliases')
        self.champions = AliasDict()
        raw_data = load_csv(data_files['crossreference']['local'])
        punc_strip = re.compile(r'[\s)(-]')
        champs = []
        all_aliases = set()
        id_index = raw_data.fieldnames.index('status')
        alias_index = raw_data.fieldnames[:id_index]
        for row in raw_data:
            if all([not i for i in row.values()]):
                continue    # empty row check
            alias_set = set()
            for col in alias_index:
                if row[col]:
                    alias_set.add(row[col].lower())
            alias_set.add(punc_strip.sub('', row['champ'].lower()))
            if all_aliases.isdisjoint(alias_set):
                all_aliases.union(alias_set)
            else:
                raise KeyError("There are aliases that conflict with previous aliases."
                        + "  First occurance with champ {}.".format(row['champ']))
            self.create_champion_class(self.bot, alias_set, **row)

    def _prepare_prestige_data(self):
        logger.debug('Preparing prestige')
        mattkraft_re = re.compile(r'(?P<star>\d)-(?P<champ>.+)-(?P<rank>\d)')
        with open(data_files['prestigeCSV']['local'], newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                champ_match = mattkraft_re.fullmatch(row.pop(0))
                if not champ_match:
                    continue
                name = champ_match.group('champ')
                star = int(champ_match.group('star'))
                rank = int(champ_match.group('rank'))

                champ = self.champions.get(name)
                if not champ:
                    logger.info('Skipping ' + name)
                    continue

                sig_len = 201 if star >= 5 else 100
                sig = [0] * sig_len
                for i, v in enumerate(row):
                    try:
                        if v and i < sig_len:
                            sig[i] = int(v)
                    except:
                        print(name, i, v, len(sig))
                        raise
                if not hasattr(champ, 'prestige_data'):
                    champ.prestige_data = {4: [None] * 5, 5: [None] * 5,6: [None] * 5, 3: [None] * 4, 2: [None]*3, 1: [None]*2}
                try:
                    champ.prestige_data[star][rank-1] = sig
                except:
                    print(name, star, rank, len(champ.prestige_data),
                            len(champ.prestige_data[star]))
                    raise

def command_arg_help(**cmdkwargs):
    def internal_func(f):
        helps = []
        for param in inspect.signature(f).parameters.values():
            if issubclass(param.annotation, commands.Converter):
                arg_help = getattr(param.annotation, 'arg_help')
                if arg_help is not None:
                    helps.append(arg_help)
        if helps:
            if f.__doc__:
                helps.insert(0, f.__doc__)
            f.__doc__ = '\n'.join(helps)
        @wraps(f)
        async def wrapper(*args, **kwargs):
            return await f(*args, **kwargs)
        return commands.command(**cmdkwargs)(wrapper)
    return internal_func

class MCOC(ChampionFactory):
    '''A Cog for Marvel's Contest of Champions'''

    def __init__(self, bot):
        self.bot = bot
        self.settings = {
                'siglvl': 1,
                'sigstep': 20,
                'table_width': 9,
                'sig_inc_zero': False,
                }
        self.data_dir="data/mcoc/{}/"
        self.shell_json=self.data_dir + "{}.json"
        self.split_re = re.compile(', (?=\w+:)')
        self.gsheet_handler = GSHandler(bot, gapi_service_creds)
        self.gsheet_handler.register_gsheet(
                name='signature',
                gkey='1kNvLfeWSCim8liXn6t0ksMAy5ArZL5Pzx4hhmLqjukg',
                local=local_files['signature'],
                postprocess=postprocess_sig_data,
            )
        self.gsheet_handler.register_gsheet(
                name='sig_coeff_4star',
                gkey='1WrAj9c41C4amzP8-jY-QhyKurO8mIeclk9C1pSvmWsk',
                local=local_files['sig_coeff_4star'],
            )
        self.gsheet_handler.register_gsheet(
                name='sig_coeff_5star',
                gkey='1VHi9MioEGAsLoZneYQm37gPkmbD8mx7HHa-zuMiwWns',
                local=local_files['sig_coeff_5star'],
            )
        self.gsheet_handler.register_gsheet(
                name='synergy',
                gkey='1Apun0aUcr8HcrGmIODGJYhr-ZXBCE_lAR7EaFg_ZJDY',
                local=local_files['synergy'],
            )
        self.gsheet_handler.register_gsheet(
            name='cdt_stats',
            gkey='1I3T2G2tRV05vQKpBfmI04VpvP5LjCBPfVICDmuJsjks',
            local='data/mcoc/cdt_stats.json',
            sheet_name='spotlightJSON',
            range_name='stats_export',
        )
        self.gsheet_handler.register_gsheet(
            name='tldr',
            gkey='1tQdQNjzr8dlSz2A8-G33YoNIU1NF8xqAmIgZtR7DPjM',
            local='data/mcoc/tldr.json',
            sheet_name='output',
            range_name='tldr_output',
            # settings=dict(column_handler='champs: to_list')
        )



    #'spotlight': {'gkey': '1I3T2G2tRV05vQKpBfmI04VpvP5LjCBPfVICDmuJsjks',
            #'local': 'data/mcoc/spotlight_test.json',
            #},
    #'crossreference': {'gkey': '1WghdD4mfchduobH0me4T6IvhZ-owesCIyLxb019744Y',
            #'local': 'data/mcoc/xref_test.json',
            #},

        logger.info("MCOC Init")
        super().__init__()

    @commands.command(name='invite', aliases=('get collector','collectorverse'),pass_context=True)
    async def get_collector(self, ctx, user: discord.User=None):
        whisper = True
        if user is None:
            user = ctx.message.author
            whisper = False
        if ctx.message.channel.is_private:
            ucolor = discord.Color.gold()
        else:
            ucolor = user.color
        joinlink = 'https://discordapp.com/oauth2/authorize?client_id=210480249870352385&scope=bot&permissions=8'
        data = discord.Embed(color=ucolor, title='INVITE COLLECTOR:sparkles:', description='', url=joinlink)
        data.description = 'Click the blue text to invite Collector to your Alliance Server.\n' \
                           'Collector requires [ **Administrator** ] permissions on your server in order to use administrative functions, moderation functions, and some Alliance management functions.\n '\
                           '\nGuildOwners are required to register on the CollectorDevTeam server in order to receive support from the CollectorDevTeam.\n' \
                           'CollectorDevTeam Server: https://discord.gg/BwhgZxk\n' \
                           '\nCollectorBot Patrons receive priority support on the CollectorDevTeam server.\n ' \
                           'Support CollectorDevTeam: https://patreon.com/collectorbot'
        data.set_author(name='CollectorDevTeam', url=COLLECTOR_ICON)
        data.set_thumbnail(url=COLLECTOR_ICON)

        if whisper:
            await self.bot.whisper(embed=data)
        else:
            await self.bot.say(embed=data)

    @commands.command(aliases=('p2f',), hidden=True)
    async def per2flat(self, per: float, ch_rating: int=100):
        '''Convert Percentage to MCOC Flat Value'''
        await self.bot.say(to_flat(per, ch_rating))

    @commands.command(name='flat') #, aliases=('f2p')) --> this was translating as "flat | f | 2 | p"
    async def flat2per(self, *, m):
        '''Convert MCOC Flat Value to Percentge
        <equation> [challenger rating = 100]'''
        if ' ' in m:
            m, cr = m.rsplit(' ',1)
            challenger_rating = int(cr)
        else:
            challenger_rating = 100
        m = ''.join(m)
        math_filter = re.findall(r'[\[\]\-()*+/0-9=.,% ]' +
            r'|acos|acosh|asin|asinh' +
            r'|atan|atan2|atanh|ceil|copysign|cos|cosh|degrees|e|erf|erfc|exp' +
            r'|expm1|fabs|factorial|floor|fmod|frexp|fsum|gamma|gcd|hypot|inf' +
            r'|isclose|isfinite|isinf|isnan|round|ldexp|lgamma|log|log10|log1p' +
            r'|log2|modf|nan|pi|pow|radians|sin|sinh|sqrt|tan|tanh', m)
        flat_val = eval(''.join(math_filter))
        p = from_flat(flat_val, challenger_rating)
        em = discord.Embed(color=discord.Color.gold(),
                title='FlatValue:',
                description='{}'.format(flat_val))
        em.add_field(name='Percentage:', value='{}\%'.format(p))
        await self.bot.say(embed=em)

    @commands.command(aliases=('compf','cfrac'), hidden=True)
    async def compound_frac(self, base: float, exp: int):
        '''Calculate multiplicative compounded fractions'''
        if base > 1:
            base = base / 100
        compound = 1 - (1 - base)**exp
        em = discord.Embed(color=discord.Color.gold(),
            title="Compounded Fractions",
            description='{:.2%} compounded {} times'.format(base, exp))
        em.add_field(name='Expected Chance', value='{:.2%}'.format(compound))
        await self.bot.say(embed=em)

    @commands.command(aliases=('update_mcoc','mu','um',), hidden=True)
    async def mcoc_update(self, fname, force=False):
        if len(fname) > 3:
            for key in data_files.keys():
                if key.startswith(fname):
                    fname = key
                    break
        if fname in data_files:
            async with aiohttp.ClientSession() as s:
                await self.cache_remote_file(fname, s, force_cache=True, verbose=True)
        else:
            await self.bot.say('Valid options for 1st argument are one of (or initial portion of)\n\t'
                    + '\n\t'.join(data_files.keys()))
            return

        self.data_struct_init()
        await self.bot.say('Summoner, I have Collected the data')

    async def say_user_error(self, msg):
        em = discord.Embed(color=discord.Color.gold(), title=msg)
        await self.bot.say(embed=em)

    @commands.command(hidden=True)
    async def mcocset(self, setting, value):
        if setting in self.settings:
            self.settings[setting] = int(value)

    @commands.command(hidden=True, aliases=['cg',])
    async def cache_gsheets(self, key=None, force=True):
         await self.update_local()
         await self.gsheet_handler.cache_gsheets(key)

    @commands.command(pass_context=True, aliases=['masteries', 'mastery'])
    async def mastery_info(self, ctx): #, word: str, rank: int = None):
        """Present Mastery Text and rank information
        /mastery info "Deep Wounds" 4
        /mastery info deepwounds 4
        /mastery info Deep Wounds 4"""
        sgd = cogs.mcocTools.StaticGameData()
        #print(len(sgd.cdt_data), len(sgd.cdt_masteries), sgd.test)
        cm = sgd.cdt_masteries
        found = False
        page_list = []
        colors = {'offense': discord.Color.red(), 'defense': discord.Color.red(),
                  'proficiencies': discord.Color.green()}



        for key in cm.keys():
            if key in ctx.message.content:
                word = key
                found = True
                break
            elif cm[key]['proper'].lower() in ctx.message.content.lower():
                word = key
                found = True
                break
            elif cm[key]['initials'] is not None and cm[key]['initials'] != "":
                if " {}".format(cm[key]['initials']) in ctx.message.content.lower():
                    word = key
                    found = True
                    break
        rank = None
        for i in range(1, 9):
            if str(i) in ctx.message.content:
                rank = i
        if not found:
            em = discord.Embed(color=discord.Color.gold(), title="Mastery Help",
                               description="Present Mastery effects, cost, and rankup information\n"
                                           "Syntax: ```/mastery <mastery> [rank]```\n"
                                           "```/mastery \"Deep Wounds\" 4\n"
                                           "/mastery deepwounds 4\n"
                                           "/mastery Deep Wounds 4```")
            offense = []
            defense = []
            utility = []
            for k in cm.keys():
                if cm[k]["category"] == "Offense":
                    offense.append(cm[k]["proper"])
                elif cm[k]["category"] == "Defense":
                    defense.append(cm[k]["proper"])
                else:
                    utility.append(cm[k]["proper"])
            em.add_field(name="Offense", value=", ".join(sorted(offense)))
            em.add_field(name="Defense", value=", ".join(sorted(defense)))
            em.add_field(name="Proficiencies", value=", ".join(sorted(utility)))
            page_list.append(em)
        elif found:
            classcores = {
                    'mutagenesis':'<:mutantcore:527924989643587584> Mastery Core X',
                    'pureskill':'<:skillcore:527924989970743316> Mastery Core of Aptitude',
                    'serumscience':'<:sciencecore:527924989194928150> Mastery Serum',
                    'mysticdispersion':'<:mysticcore:527924989400186882> Mystical Mastery',
                    'cosmicawareness':'<:cosmiccore:527924988661989397> Cosmic Mastery',
                    'collartech':'<:techcore:527924989777805322> Mastery Core 14',
                    'detectmutant':'<:mutantcore:527924989643587584> Mastery Core X',
                    'detectskill':'<:skillcore:527924989970743316> Master Core of Aptitude',
                    'detectscience':'<:sciencecore:527924989194928150> Mastery Serum',
                    'detectmystic':'<:mysticcore:527924989400186882> Mystical Mastery',
                    'detectcosmic':'<:cosmiccore:527924988661989397> Cosmic Mastery',
                    'detecttech':'<:techcore:527924989777805322> Mastery Core 14'
                }
            classcorekeys = classcores.keys()
            unlocks = {'ucarbs': '<:carbcore:527924990159355904> Carbonium Core(s)', 'uclass': ' {} Core(s)'.format(classcores[key] if key in classcores else 'Class'), 'ustony': '<:stonycore:416405764937089044> Stony Core(s)', 'uunits': '<:units:344506213335302145> Units'}
            rankups = {'rgold': '<:gold:344506213662326785> Gold', 'runit': '<:units:344506213335302145> Unit(s)'}
            maxranks = cm[key]['ranks']
            titled = cm[key]['icon']+' '+cm[key]['proper']+ ' {}/'+str(maxranks)
            embedcolor = colors[cm[key]['category'].lower()]
            desc = cm[key]['text']
            cumulative_unlock = {'ucarbs':0, 'uclass': 0, 'ustony': 0, 'uunits':0}
            cumulative_rankups = {'rgold':0, 'runit':0}
            for r in range(1, maxranks + 1):
                mrank = str(r)
                effects = list(cm[key][mrank]['effects'])
                print('mastery desc = ' + desc)
                print('mastery effects = '+str(effects))
                # for i in range(1, len(effects)):
                #     desc=desc.format(effects[i-1])
                desceffects=desc.format(*effects)
                print('mastery desc(effects)' + str(desceffects))
                em = discord.Embed(color=embedcolor, title=titled.format(r), description = desceffects)
                em.set_footer(text='CollectorDevTeam Dataset', icon_url=COLLECTOR_ICON)
                unlock_costs = []
                rankup_costs = []
                cum_unlock_costs = []
                cum_rankup_costs = []
                for u in unlocks.keys():
                    if cm[key][mrank][u] > 0:
                        cumulative_unlock[u] = cumulative_unlock[u] + cm[key][mrank][u]
                        unlock_costs.append('{} {}'.format(cm[key][mrank][u], unlocks[u]))
                        cum_unlock_costs.append('{} {}'.format(cumulative_unlock[u], unlocks[u]))
                for ru in rankups.keys():
                    if cm[key][mrank][ru] > 0:
                        cumulative_rankups[ru] = cumulative_rankups[ru] + cm[key][mrank][ru]
                        rankup_costs.append('{} {}'.format(cm[key][mrank][ru], rankups[ru]))
                if len(unlock_costs) >0:
                    unlock_units = cm[key][mrank]['ucarbs']*550+cm[key][mrank]['ustony']*135+cm[key][mrank]['uunits']
                    em.add_field(name='Unlock Cost : {} <:units:344506213335302145>'.format(unlock_units), value='\n'.join(unlock_costs), inline=False)
                if len(rankup_costs) > 0:
                    em.add_field(name='Rank Up Cost', value='\n'.join(rankup_costs), inline=False)
                if len(cum_unlock_costs) >0:
                    cumulative_units = cumulative_unlock['ucarbs']*550+cumulative_unlock['ustony']*135+cumulative_unlock['uunits']
                    em.add_field(name='Cumulative Unlock Cost : {} <:units:344506213335302145>'.format(cumulative_units), value='\n'.join(cum_unlock_costs), inline=False)
                if len(cum_rankup_costs) > 0:
                    em.add_field(name='Cumulative Rank Up Cost', value='\n'.join(cum_rankup_costs), inline=False)
                em.add_field(name='Prestige Bump', value='{} %'.format(round(cm[key][mrank]['pibump']*100,3)), inline=False)
                page_list.append(em)


        if len(page_list) > 0:
            menu = PagesMenu(self.bot, timeout=120, delete_onX=True, add_pageof=True)
            if rank == None:
                page_number = 0
            elif maxranks == 0:
                page_number = 0
            elif rank >= maxranks:
                page_number = maxranks -1
            else:
                page_number = max(rank-1, 0)
            await menu.menu_start(pages=page_list, page_number=page_number)

    @commands.command(pass_context=True, aliases=['modok',], hidden=True)
    async def modok_says(self, ctx, *, word:str = None):
        await self.bot.delete_message(ctx.message)
        await raw_modok_says(self.bot, ctx.message.channel, word)

    # @checks.admin_or_permissions(manage_server=True)
    @commands.command(pass_context=True, aliases=['nbs',])
    async def nerfbuffsell(self, ctx):
        '''Random draw of 3 champions.
        Choose one to Nerf, one to Buff, and one to Sell'''
        colors=[discord.Color.teal(), discord.Color.dark_teal(),
                discord.Color.green(), discord.Color.dark_green(),
                discord.Color.blue(), discord.Color.dark_blue(),
                discord.Color.purple(), discord.Color.dark_purple(),
                discord.Color.magenta(), discord.Color.dark_magenta(),
                discord.Color.gold(), discord.Color.dark_gold(),
                discord.Color.orange(), discord.Color.dark_orange(),
                discord.Color.red(), discord.Color.dark_red(),
                discord.Color.lighter_grey(), discord.Color.dark_grey(),
                discord.Color.light_grey(), discord.Color.darker_grey()]
        rcolor=random.choice(colors)
        selected = []
        embeds = []
        emojis = ['🇳', '🇧', '🇸']
        em1 = discord.Embed(color=rcolor, title='Nerf, Buff, or Sell', description='')
        em2 = discord.Embed(color=rcolor, description='',
                title='Select one to Nerf, one to Buff, and one to Sell. Explain your choices',
            )

        while len(selected) < 3:
            name_id = random.choice(list(self.champions.values()))
            champ = await self.get_champion(name_id.mattkraftid)
            if champ not in selected:
                if champ.status == 'released':
                    selected.append(champ)
                    em = discord.Embed(color=champ.class_color, title=champ.full_name)
                    em.set_thumbnail(url=champ.get_avatar())
                    embeds.append(em)
        try:
            await self.bot.say(embed=em1)
            for em in embeds:
                message = await self.bot.say(embed=em)
                for emoji in emojis:
                    await self.bot.add_reaction(message=message, emoji=emoji)
                    # await asyncio.sleep(1)
            await self.bot.say(embed=em2)
        except:
            await self.bot.say('\n'.join(s.full_name for s in selected))



    # START CHAMP GROUP
    #
    @commands.group(pass_context=True, aliases=['champs',])
    async def champ(self, ctx):
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @champ.command(pass_context=True, name='featured',aliases=['feature',])
    async def champ_featured(self, ctx, *, champs : ChampConverterMult):
        '''Champion Featured image'''
        for champ in champs:
            released = await self.check_release(ctx, champ)
            if released:
                em = discord.Embed(color=champ.class_color, title=champ.full_name)
                em.set_author(name=champ.full_name + ' - ' + champ.short, icon_url=champ.get_avatar())
                em.set_image(url=champ.get_featured())
                await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='portrait', aliases=['avatar',])
    async def champ_portrait(self, ctx, *, champs : ChampConverterMult):
        '''Champion portraits'''
        for champ in champs:
            released = await self.check_release(ctx, champ)
            if released:
                em = discord.Embed(color=champ.class_color, title=champ.full_name)
                em.set_author(name=champ.full_name + ' - ' + champ.short, icon_url=champ.get_avatar())
                em.set_image(url=champ.get_avatar())
                print(champ.get_avatar())
                await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='bio', aliases=('biography',))
    async def champ_bio(self, ctx, *, champ : ChampConverterDebug):
        '''Champio Bio'''
        try:
            bio_desc = await champ.get_bio()
        except KeyError:
            await self.say_user_error("Cannot find bio for Champion '{}'".format(champ.full_name))
            return
        released = await self.check_release(ctx, champ)
        if released:
            em = discord.Embed(color=champ.class_color, title='Champion Biography',
                    description=bio_desc)
            em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
            em.add_field(name='hashtags',
                    value=chat.box(' '.join(champ.class_tags.union(champ.tags))),inline=False)
            em.add_field(name='Shortcode', value=champ.short,inline=False)
            em.set_thumbnail(url=champ.get_avatar())
            em.set_footer(text='MCOC Game Files', icon_url=KABAM_ICON)
            await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='duel')
    async def champ_duel(self, ctx, champ : ChampConverter):
        '''Duel & Spar Targets'''
        #dataset=data_files['duelist']['local']
        # released = await self.check_release(ctx, champ)
        released = True
        author = ctx.message.author
        if released:
            gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
            sh = gc.open_by_key('1FZdJPB8sayzrXkE3F2z3b1VzFsNDhh-_Ukl10OXRN6Q')
            ws = sh.worksheet('title', 'DataExport')
            data = ws.get_all_records()
            if not len(data):
                await self.bot.say("Data did not get retrieved")
                raise IndexError

            DUEL_SPREADSHEET='https://docs.google.com/spreadsheets/d/1FZdJPB8sayzrXkE3F2z3b1VzFsNDhh-_Ukl10OXRN6Q/view#gid=61189525'
            em = discord.Embed(color=champ.class_color, title='Duel & Spar Targets', url=DUEL_SPREADSHEET)
            em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
            em.set_thumbnail(url=champ.get_featured())
            em.set_footer(text='CollectorDevTeam + RC51\'s Duel Targets',
                    icon_url=GSHEET_ICON)

            targets = []
            for duel in data:    # single iteration through the data
                if duel['unique']=='':
                    continue
                else:
                    uniq = duel['unique']
                    star, duel_champ, rank = int(uniq[:1]), uniq[2:-2], int(uniq[-1:])
                    star, duel_champ, rank = int(uniq[:1]), uniq[2:-2], int(uniq[-1:])
                    if duel_champ == champ.mattkraftid:
                        # targets.append('{}{} {} {} : {}'.format(star, champ.star_char,
                        #             duel['maxlevel'],
                        #             champ.full_name,
                        #             duel['username']))
                        targets.append('{} : {}'.format(duel['champion'], duel['username']))
            targets.sort()
            #for star in range(3,7):
                #for rank in range(1,6):
                    #key = '{0}-{1}-{2}'.format(star, champ.full_name, rank)
                    #for data in get_csv_rows(dataset, 'unique', key):#champ.unique):
                        #targets.append( '{}{} {} {} : {}'.format(star, champ.star_char, data['maxlevel'], champ.full_name, data['username']))
            if len(targets) > 0:
                em.description='\n'.join(targets)
            else:
                em.description='Target not found!\nAdd one to the Community Spreadhseet!\n[bit.ly/DuelTargetForm](http://bit.ly/DuelTargetForm)'
                em.url = 'http://bit.ly/DuelTargetForm'
            em.add_field(name='Shortcode', value=champ.short, inline=False)
            await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='about', aliases=('about_champ',))
    async def champ_about(self, ctx, *, champ : ChampConverterRank):
        '''Champion Base Stats'''
        released = await self.check_release(ctx, champ)
        if released:
            data = champ.get_spotlight(default='x')
            # title = 'Base Attributes for {}'.format(champ.verbose_str)
            em = discord.Embed(color=champ.class_color,
                    title='Base Attributes')
            em.set_author(name=champ.verbose_str, icon_url=champ.get_avatar())
            titles = ('Health', 'Attack', 'Crit Rate', 'Crit Dmg', 'Armor', 'Block Prof')
            keys = ('health', 'attack', 'critical', 'critdamage', 'armor', 'blockprof')
            # xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)

            if champ.debug:
                em.add_field(name='Attrs', value='\n'.join(titles))
                em.add_field(name='Values', value='\n'.join([data[k] for k in keys]), inline=True)
                em.add_field(name='Added to PHC', value=champ.basic4)
            else:
                stats = [[titles[i], data[keys[i]]] for i in range(len(titles))]
                em.add_field(name='Base Stats',
                    value=tabulate(stats, width=11, rotate=False, header_sep=False))
            # em = await self.get_synergies([champ], embed=em)
            if champ.infopage != 'none':
                em.add_field(name='Infopage',value='<{}>'.format(champ.infopage),inline=False)
            else:
                em.add_field(name='Infopage',value='No spotlight post from Kabam',inline=False)
                em.add_field(name='hashtags',
                        value=chat.box(' '.join(champ.class_tags.union(champ.tags))))
            em.add_field(name='Shortcode', value=champ.short)
            em.set_footer(text='CollectorDevTeam Dataset', icon_url=COLLECTOR_ICON)
            em.set_thumbnail(url=champ.get_avatar())
            await self.bot.say(embed=em)


    @champ.command(pass_context=True, name='tldr')
    async def champ_tldr(self, ctx, champ: ChampConverterDebug, force=False):
        '''UMCOC crowdsourced TLDR how-to use'''
        key='tldr'
        if champ.debug:
            force = True
        # sgd = cogs.mcocTools.StaticGameData()
        if force is True:
            await self.gsheet_handler.cache_gsheets(key)
        # now = datetime.datetime.now().date()
        now = datetime.now().date()
        if os.path.exists('data/mcoc/tldr.json'):
            # filetime = datetime.datetime.fromtimestamp(os.path.getctime('data/mcoc/tldr.json'))
            filetime = datetime.fromtimestamp(os.path.getctime('data/mcoc/tldr.json'))
            if filetime.date() != now:
                await self.gsheet_handler.cache_gsheets(key)
        else:
            await self.gsheet_handler.cache_gsheets(key)
        tldr = dataIO.load_json('data/mcoc/tldr.json')

        if ctx.message.channel.is_private:
            ucolor = discord.Color.gold()
        else:
            ucolor = ctx.message.author.color
        data = discord.Embed(color=ucolor, title='Abilities are Too Long; Didn\'t Read', url=PATREON)
        k = champ.full_name
        package = ''
        if k in tldr.keys():
            if 'sig' in tldr[k].keys():
                package += 'Signature Ability Required?\n'
                package += tldr[k]['sig']+'\n\n'
                # data.add_field(name="Signature Ability needed?", value=tldr[k]['sig'], inline=False)
            for i in range(1, 4):
                uid = 'user{}'.format(i)
                tid = 'tldr{}'.format(i)
                if uid in tldr[k] and tldr[k][uid] != "":
                    package += '**{}** says:\n'.format(tldr[k][uid])
                    package += '{}\n------------------------------\n'.format(tldr[k][tid])
                    # data.add_field(name='{} says:'.format(tldr[k][uid]), value=tldr[k][tid], inline=False)
            if 'user4' not in tldr[k].items():
                package += 'Don\'t like that advice? \n\n[Click here to add a TLDR!](https://forms.gle/EuhWXyE5kxydzFGK8)'
                # data.description = 'Don\'t like that advice? \n\n[Click here to add a TLDR!](https://forms.gle/EuhWXyE5kxydzFGK8)'
        else:
            package += 'Don\'t like that advice? \n\n[Click here to add a TLDR!](https://forms.gle/EuhWXyE5kxydzFGK8)'
            # data.description = 'No information.  \nAdd a TLDR here: [TLDR Form](https://forms.gle/EuhWXyE5kxydzFGK8)'
        data.add_field(name='Shortcode', value=champ.short, inline=False)
        data.set_footer(text='Requested by {}'.format(ctx.message.author.display_name), icon_url=COLLECTOR_ICON)
        data.set_thumbnail(url=champ.get_avatar())
        data.description = package
        await self.bot.say(embed=data)


    @commands.has_any_role('CollectorDevTeam','CollectorSupportTeam','CollectorPartners')
    @champ.command(pass_context=True, name='export', hidden=True)
    async def champ_list_export(self, ctx, *, hargs=''):
        '''List of #hargs champions in name order.

        hargs:  [attribute_args] [hashtags]
        The optional attribute arguments can be in any order, with or without spaces.
            <digit>* specifies star <default: 4>
            r<digit> specifies rank <default: 5>
            s<digit> specifies signature level <default: 99>

        Examples:
            /champ list    (all 4* champs rank5, sig99)
            /champ list 5*r3s20 #bleed   (all 5* bleed champs at rank3, sig20)
        '''
        guild = await self.check_guild(ctx)
        if not guild:
            await self.bot.say('This server is unauthorized.')
            return
        else:
            # harglist = self.bot.user + hargs
            # hargs = await hook.HashtagRankConverter(ctx, hargs).convert() #imported from hook
            roster = hook.HashtagRosterConverter(ctx.bot, hargs).convert()
            #await self.update_local()
            # roster = hargs.roster.filter_champs(hargs.tags)
            # filtered = roster.filter_champs(hargs.attrs.copy())
            strs = [champ.full_name for champ in roster]##sorted(filtered, reverse=True, key=attrgetter('full_name'))]
            package = '\n'.join(strs)
            print(package)
            pages = chat.pagify(package, page_length=2000)
            for page in pages:
                await self.bot.say(chat.box(page))



    @champ.command(pass_context=True, name='list')
    async def champ_list(self, ctx, *, hargs=''):
        '''List of all champions in prestige order.

        hargs:  [attribute_args] [hashtags]
        The optional attribute arguments can be in any order, with or without spaces.
            <digit>* specifies star <default: 4>
            r<digit> specifies rank <default: 5>
            s<digit> specifies signature level <default: 99>

        Examples:
            /champ list    (all 4* champs rank5, sig99)
            /champ list 5*r3s20 #bleed   (all 5* bleed champs at rank3, sig20)
        '''
        #hargs = await hook.HashtagRankConverter(ctx, hargs).convert() #imported from hook
        #roster = hook.ChampionRoster(self.bot, self.bot.user, attrs=hargs.attrs)
        #await roster.display(hargs.tags)
        sgd = StaticGameData()
        aliases = {'#var2': '(#5star | #6star) & #size:xl', '#poisoni': '#poisonimmunity'}
        roster = await sgd.parse_with_attr(ctx, hargs, hook.ChampionRoster, aliases=aliases)
        if roster is not None:
            await roster.display()

    @champ.command(pass_context=True, name='released', aliases=('odds','chances',))
    async def champ_released(self, ctx, champ: ChampConverter=None):
        '''Champion Release Date & Crystal Odds'''
        print('check_release')
        # released = await self.check_release(ctx, champ)
        if champ is None:
            data = discord.Embed(color=discord.Color.gold(),
                                 title='CollectorVerse Help', description='Syntax:'
                                                                          ''
                                                                          '/champ odds <champion>'
                                                                           'Check out this video for help')

            await self.bot.say(embed=data)
            await self.bot.say('https://youtu.be/ewZiaL0Mcts')
            return

        released = True
        if released:
            em = discord.Embed(color=champ.class_color, title='{} | Released {}'.format(champ.full_name, champ.released),
                               url=SPOTLIGHT_DATASET, description='Release Dates & Estimated Crystal Opening Odds')
            daily4 = 0.10
            daily3 = 0.30
            daily2 = 0.60
            p2 = float(0.70)
            p3 = float(0.25)
            p4 = float(0.05)
            gmc = {3: float(0.80), 4: float(0.15), 5: float(0.05)}
            cav = {3: float(0.50), 4: float(0.38), 5: float(0.11), 6: float(0.01)}
            em.add_field(name='PHC Drop Rates', value='2★ {} %\n3★ {} %\n4★ {} %\n'
                         .format(round(p2*100, 0), round(p3*100, 0), round(p4*100), 0))
            em.add_field(name='Grandmaster Drop Rates', value='3★ {} %\n4★ {} %\n5★ {} %\n'
                         .format(round(gmc[3]*100, 0), round(gmc[4]*100, 0), round(gmc[5]*100), 0))
            em.add_field(name='Cavalier Drop Rates', value='3★ {} %\n4★ {} %\n5★ {} %\n6★ {} %\n'
                         .format(round(cav[3] * 100, 0), round(cav[4] * 100, 0),
                                 round(cav[5] * 100, 0), round(cav[6] * 100, 0)), inline=False)
            # em.add_field(name='Featured Grandmaster Drop Rates', value='3★ {} %\n4★ {} %\n5★ {} %\n'
            #              .format(round(fgmc[3]*100, 0), round(fgmc[4]*100, 0), round(fgmc[5]*100), 0))
            # em.add_field(name='Release Date', value='{0.released}'.format(champ), inline=False)
            if champ.chance4 is not None and float(champ.chance4) > 0:
                phc2 = round(p2*float(champ.chance4), 4)
                phc3 = round(p3*float(champ.chance4), 4)
                phc4 = round(p4*float(champ.chance4), 4)
                em.add_field(name='PHC Odds', value='2★ {} %\n3★ {} %\n4★ {} %'.format(phc2, phc3, phc4))
            if champ.chance5b is not None and float(champ.chance5b) > 0:
                gmc5 = round(float(champ.chance5b)*gmc[5], 4)
                gmc4 = round(float(champ.chance4)*gmc[4], 4)
                gmc3 = round(float(champ.chance4)*gmc[3], 4)
                em.add_field(name='Grandmaster Crystal Odds', value='3★ {} %\n4★ {} %\n5★ {} %'.format(gmc3, gmc4, gmc5), inline=False)
            if champ.chance6b is not None and float(champ.chance6b) > 0:
                chance6 = round(float(champ.chance6b),4)
                cav6 = round(float(champ.chance5b) * cav[6], 4)
                cav5 = round(float(champ.chance5b) * cav[5], 4)
                cav4 = round(float(champ.chance4) * cav[4], 4)
                cav3 = round(float(champ.chance4) * cav[3], 4)
                em.add_field(name='Cavalier Crystal Odds', value='3★ {} %\n4★ {} %\n5★ {} %\n6★ {} %'.format(cav3, cav4, cav5, cav6), inline=False)
            if champ.chance4 is not None and float(champ.chance4) > 0:
                chance4 = round(float(champ.chance4), 4)
                em.add_field(name='4★ Basic Odds', value='{0} %'.format(chance4), inline=True)
            elif champ.basic4 is not None:
                em.add_field(name='Expected 4★ Basic & PHC Release', value=champ.basic4)
            if champ.chance5f is not None and float(champ.chance5f) > 0:
                chance5 = round(float(champ.chance5f), 4)
                em.add_field(name='5★ Featured Odds', value='{0} %'.format(chance5), inline=True)
            if champ.chance5b is not None and float(champ.chance5b) > 0:
                chance5 = round(float(champ.chance5b), 4)
                em.add_field(name='5★ Basic Odds', value='{0} %'.format(chance5), inline=True)
            elif champ.basic5 is not None:
                em.add_field(name='Expected 5★ Basic Release', value=champ.basic5)
            if champ.chance6f is not None and float(champ.chance6f) > 0:
                chance6=round(float(champ.chance6f),4)
                em.add_field(name='6★ Featured Odds', value='{0} %'.format(chance6), inline=True)
            if champ.chance6b is not None and float(champ.chance6b) > 0:
                chance6 = round(float(champ.chance6b),4)
                em.add_field(name='6★ Basic Odds', value='{0} %'.format(chance6), inline=True)
            elif champ.basic6 is not None:
                em.add_field(name='Expected 6★ Basic Release', value=champ.basic6)


            em.add_field(name='Shortcode', value=champ.short, inline=True)
            em.set_thumbnail(url=champ.get_featured())
            em.set_author(name='CollectorDevTeam', url=COLLECTOR_ICON)
            em.set_footer(text='Requested by {}'.format(ctx.message.author.display_name),
                          icon_url=ctx.message.author.avatar_url)
            await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='sig', aliases=['signature',])
    async def champ_sig(self, ctx, *, champ : ChampConverterSig):
        '''Champion Signature Ability'''
        released = await self.check_release(ctx, champ)
        if not released:
            await self.bot.say("Champion {} is not released yet".format(champ.fullname))
            return
        appinfo = await self.bot.application_info()
        try:
            title, desc, sig_calcs = await champ.process_sig_description(
                    isbotowner=ctx.message.author == appinfo.owner)
            #print(desc)
        except KeyError:
            await champ.missing_sig_ad()
            if champ.debug:
                raise
            return
        except SignatureSchemaError as e:
            await self.bot.say("Technical Difficulties with Signature Retrieval."
                    "\n'{}' needs a bit of cleanup".format(champ.full_name)
                )
            if champ.debug:
                await self.bot.say(chat.box(str(e)))
            return
        if title is None:
            return
        em = discord.Embed(color=champ.class_color, title='Signature Ability')
        em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
        em.add_field(name=title, value=champ.star_str)
        em.add_field(name='Signature Level {}'.format(champ.sig),
                value=desc.format(d=sig_calcs))
        em.add_field(name='Shortcode', value=champ.short)
        em.set_footer(text='MCOC Game Files', icon_url=KABAM_ICON)
        em.set_thumbnail(url=champ.get_avatar())
        await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='sigreport', hidden=False)
    async def champ_sig_report(self, ctx):
        '''Check All Champion Signature Abilities'''
        bad_champs = defaultdict(list)
        for champ_class in self.champions.values():
            champ = champ_class()
            if not champ.is_user_playable:
                continue
            try:
                title, desc, sig_calcs = await champ.process_sig_description(
                        isbotowner=True, quiet=True)
            except Exception as e:
                bad_champs[type(e)].append(champ.full_name)
        #pages = chat.pagify('\n'.join(bad_champ))
        page_list = []
        for err, champs in bad_champs.items():
            em = discord.Embed(title='Champion Sig Errors')
            em.add_field(name=err.__name__, value='\n'.join(champs))
            em.set_footer(text='MCOC Game Files', icon_url=KABAM_ICON)
            page_list.append(em)
        menu = PagesMenu(self.bot, timeout=120, delete_onX=True, add_pageof=True)
        await menu.menu_start(page_list)

    @champ.command(pass_context=True, name='sigplot', hidden=True)
    async def champ_sigplot(self,ctx,*, champ: ChampConverterSig):

        try:
            # try:
            #     plt.axis()
            # except:
            # plt.plot([1,2,3,4],[1,4,9,16], 'r-')
            x = [1, 20, 40, 60, 80, 99]
            y1 = [69, 182.54, 202.82, 224.2, 235.11, 243.20]
            y2 = [23.92, 65.61, 75.39, 81.14, 85.22, 88.25]
            plt.plot(x, y1, 'rs', label='line 1')
            plt.plot(x, y2, 'go-', label='line 2')
            plt.axis()
            plt.legend()
            plt.xlabel('Signature Ability Level')
            plt.ylabel('Signature Ability Effect')
            plt.suptitle('Sig Plot [Test]')
            # plt.show()
            plt.draw()
            plt.savefig('data/mcoc/sigtemp.png', format='png', dpi=90)
            await self.bot.upload('data/mcoc/sigtemp.png')
            os.remove('data/mcoc/sigtemp.png')
        except:
            print('champ_sigplot nothing happened')


    @champ.command(pass_context=True, name='stats', aliases=('stat',))
    async def champ_stats(self, ctx, *, champs : ChampConverterMult):
        '''Champion(s) Base Stats'''
        # sgd = cogs.mcocTools.StaticGameData()
        now = datetime.now().date()
        if os.path.exists('data/mcoc/cdt_stats.json'):
            # filetime = datetime.datetime.fromtimestamp(os.path.getctime('data/mcoc/tldr.json'))
            filetime = datetime.fromtimestamp(os.path.getctime('data/mcoc/cdt_stats.json'))
            if filetime.date() != now:
                await self.gsheet_handler.cache_gsheets('cdt_stats')
        else:
            await self.gsheet_handler.cache_gsheets('cdt_stats')
        cdt_stats = dataIO.load_json('data/mcoc/cdt_stats.json')
        for champ in champs:
            released = await self.check_release(ctx, champ)
            if released:
                data = cdt_stats
                # data = champ.get_spotlight(default='x')
                embeds =[]
                em = discord.Embed(color=champ.class_color, title='Champion Stats',url=SPOTLIGHT_SURVEY)
                em.set_author(name=champ.verbose_str, icon_url=champ.get_avatar())
                em.set_footer(text='CollectorDevTeam Dataset', icon_url=COLLECTOR_ICON)
                titles = ('Health', 'Attack', 'Crit Rate', 'Crit Dmg', 'Armor Penetration', 'Block Penetration', 'Crit Resistance', 'Armor', 'Block Prof')
                keys = ('health', 'attack', 'critical', 'critdamage', 'armor_pen', 'block_pen', 'crit_resist', 'armor', 'blockprof')
                # xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)
                # if champ.debug:
                #     em.add_field(name='Attrs', value='\n'.join(titles))
                #     em.add_field(name='Values', value='\n'.join([data[k] for k in keys]), inline=True)
                #     em.add_field(name='Added to PHC', value=xref['4basic'])
                # else:
                # stats = [[titles[i], data[champ.unique, keys[i]]] for i in range(len(titles))]
                # for i, k in titles, keys:
                # for i in range(len(titles)):
                    # k = keys[i]
                    # stats = [i, data[champ.unique][k]]
                    # stats = [[titles[i], data[champ.unique][k]]]
                stats = [[titles[i], data[champ.unique][keys[i]]] for i in range(len(titles))]
                em.add_field(name='Base Stats', value=tabulate(stats, width=18, rotate=False, header_sep=False), inline=False)
                em.add_field(name='Shortcode',value=champ.short)
                # em.set_thumbnail(url=champ.get_featured())
                embeds.append(em)

                em2 = discord.Embed(color=champ.class_color, title='Champion Stats', url=SPOTLIGHT_SURVEY)
                em2.set_author(name=champ.verbose_str, icon_url=champ.get_avatar())
                em2.set_footer(text='CollectorDevTeam Dataset', icon_url=COLLECTOR_ICON)
                # em2.set_thumbnail(url=champ.get_featured())
                flats = []
                # flats.append(data[keys[0]])
                # flats.append(data[keys[1]])
                flats.append(data[champ.unique]['health'])
                flats.append(data[champ.unique]['attack'])
                # if data[keys[2]] == 'x':
                if data[champ.unique]['critical'] == 'x':
                    flats.append('x')
                else:
                    # flats.append('% {}'.format(from_flat(int(data[champ.unique][keys[2]].replace(',','')), int(champ.chlgr_rating))))
                    flats.append('% {}'.format(
                        from_flat(int(data[champ.unique][keys[2]]), int(champ.chlgr_rating))))
                if data[champ.unique]['critdamage'] == 'x':
                # if data[keys[3]] == 'x':
                    flats.append('x')
                else:
                    critdmg = round(
                        0.5 + 5 * from_flat(int(data[champ.unique][keys[3]]), int(champ.chlgr_rating)),
                        2)
                    # critdmg=round(0.5+5*from_flat(int(data[champ.unique][keys[3]].replace(',','')), int(champ.chlgr_rating)),2)
                    flats.append('% {}'.format(critdmg))
                # for k in range(4, len(keys)):
                for k in ('armor_pen', 'block_pen', 'crit_resist', 'armor', 'blockprof'):
                    if data[champ.unique][k] == 'x':
                        flats.append('x')
                    else:
                        flats.append('% {}'.format(from_flat(int(data[champ.unique][k]), int(champ.chlgr_rating))))
                        # flats.append('% {}'.format(from_flat(int(data[champ.unique][keys[k]].replace(',','')), int(champ.chlgr_rating))))
                pcts = [[titles[i], flats[i]] for i in range(len(titles))]
                em2.add_field(name='Base Stats %', value=tabulate(pcts, width=19, rotate=False, header_sep=False), inline=False)
                em2.add_field(name='Shortcode', value=champ.short)
                embeds.append(em2)
                try:
                    menu = PagesMenu(self.bot, timeout=120, delete_onX=True, add_pageof=True)
                    await menu.menu_start(embeds)                # for page in pages:
                except:
                    print('PagesMenu failure')
                    await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='update', aliases=('add', 'dupe'), hidden=True)
    async def champ_update(self, ctx, *, args):
        '''Not a real command'''
        msg = '`{0}champ update` does not exist.\n' \
            + '`{0}roster update` is probably what you meant to do'
        prefixes = tuple(self.bot.settings.get_prefixes(ctx.message.server))
        await self.bot.say(msg.format(prefixes[0]))

    def set_collectordev_footer(self, pack, author=None):
        try:
            for embed in pack:
                if author is None:
                    embed.set_footer(text='CollectorDevTeam', icon_url=COLLECTOR_ICON)
                else:
                    embed.set_footer(text='Requested by {}'.format(author.display_name), icon_url=author.avatar_url)
        except TypeError:
            pack.set_footer(text='CollectorDevTeam', icon_url=COLLECTOR_ICON)

    # @champ.command(pass_context=True, name='triggers', aliases=['synw',])
    # async def champ_syn_with(self, ctx, *, champ: ChampConverter):
    #     '''Find Synergies triggered by Champion'''
    #     if champs[0].debug:
    #         await self.gsheet_handler.cache_gsheets('synergy')
    #     syn_data = dataIO.load_json(local_files['synergy'])['SynExport']
    #     syn_keys = syn_data.keys()
    #     syn_list =[]
    #     for activation in syn_keys:
    #         if champ.full_name in activation['triggers']:
    #             syn_list.append('{} from {}'.format(syn_keys[activation][synergycode]), activation)


    @champ.command(pass_context=True, name='synergies', aliases=['syn',])
    async def champ_synergies(self, ctx, *, champs: ChampConverterMult):
        '''Champion(s) Synergies'''
        syn_champs = []
        for champ in champs:
            released = await self.check_release(ctx, champ)
            if released:
                syn_champs.append(champ)
        if len(syn_champs) > 0:
            pack = await self.get_synergies(syn_champs, embed=None, author=ctx.message.author)
            ## should return a list of embeds

            # self.set_collectordev_footer(pack, ctx.message.author)
            menu = PagesMenu(self.bot, timeout=120)
            await menu.menu_start(pack)
        else:
            return
        #await self.bot.say(embed=em)

    async def get_synergies(self, champs, embed=None, author=None):
        '''If Debug is sent, data will refresh'''
        if champs[0].debug:
            await self.gsheet_handler.cache_gsheets('synergy')
        syn_data = dataIO.load_json(local_files['synergy'])
        pack = []
        if len(champs) > 1:
            pack = await self.get_multiple_synergies(champs, syn_data, pack=pack, author=author)
        elif len(champs) == 1:
            pack = await self.get_single_synergies(champs[0], syn_data, pack=pack, author=author)
            pack = await self.get_reverse_synergies(champs[0], syn_data, pack=pack, author=author)
        return pack

    async def get_single_synergies(self, champ, syn_data, embed=None, pack=None, author=None):
        if embed is None:
            embed = discord.Embed(color=champ.class_color, title='These champions activate {} Synergies'.format(champ.full_name))
            embed.set_author(name=champ.star_name_str, icon_url=champ.get_avatar())
            embed.set_thumbnail(url=champ.get_featured())
            if author is None:
                embed.set_footer(text='CollectorDevTeam', icon_url=COLLECTOR_ICON)
            else:
                embed.set_footer(text='Requested by {}'.format(author.display_name), icon_url=author.avatar_url)

        champ_synergies = syn_data['SynExport'][champ.full_name]
        if champ_synergies is not None:
            for lookup, data in champ_synergies.items():
                if champ.star != data['stars']:
                    continue
                syneffect = syn_data['SynergyEffects'][data['synergycode']]
                triggers = data['triggers']
                effect = syneffect['rank{}'.format(data['rank'])]
                try:
                    txt = syneffect['text'].format(*effect)
                except:
                    print(syneffect['text'], effect)
                    raise
                embed.add_field(name='{}'.format(syneffect['synergyname']),
                        value='+ **{}**\n{}\n'.format(', '.join(triggers), txt),
                        inline=False)
            if pack is None:
                return embed
            else:
                pack.append(embed)
                return pack
        return None


    async def get_reverse_synergies(self, champ, syn_data, pack=None, author=None):
        description = ''
        found = []
        for c in syn_data['SynExport'].keys():
            champ_synergies = syn_data['SynExport'][c]
            for key, data in champ_synergies.items():
                # if champ.star != data['stars']:
                #     continue
                redundant = '{}{}{}'.format(data['synergycode'], data['ranks'], data['triggers'])
                if champ.full_name in data['triggers'] and redundant not in found:
                    syneffect = syn_data['SynergyEffects'][data['synergycode']]
                    # triggers = data['triggers']
                    effect = syneffect['rank{}'.format(data['rank'])]
                    try:
                        txt = syneffect['text'].format(*effect)
                    except:
                        print(syneffect['text'], effect)
                        raise
                    found.append(redundant)
                    description += '{} | {} {}\n'.format(syneffect['synergyname'], c, data['ranks'])
                    description += '{}\n\n'.format(txt)

        pages = chat.pagify(description)
        for page in pages:
            embed = discord.Embed(color=champ.class_color, title='{} Activates these Synergies:'.format(champ.full_name), description=page)
            embed.set_author(name=champ.star_name_str, icon_url=champ.get_avatar())
            embed.set_thumbnail(url=champ.get_featured())
            if author is None:
                embed.set_footer(text='CollectorDevTeam', icon_url=COLLECTOR_ICON)
            else:
                embed.set_footer(text='Requested by {}'.format(author.display_name), icon_url=author.avatar_url)
            pack.append(embed)
        return pack



        #     I am looking for champ.full_name in value[triggers]
        #  If I find champ.full_name in value[triggers], add value[unique] to foundlist
        #      and add value[synergycode] + value[rank] to redundants


        # champ_synergies = syn_data['SynExport'][champ.full_name]
        # for lookup, data in champ_synergies.items():
        #     if champ.star != data['stars']:
        #         continue
        #     syneffect = syn_data['SynergyEffects'][data['synergycode']]
        #     triggers = data['triggers']
        #     effect = syneffect['rank{}'.format(data['rank'])]
        #     try:
        #         txt = syneffect['text'].format(*effect)
        #     except:
        #         print(syneffect['text'], effect)
        #         raise
        #     embed.add_field(name='{}'.format(syneffect['synergyname']),
        #             value='+ **{}**\n{}\n'.format(', '.join(triggers), txt),
        #             inline=False)

    async def get_multiple_synergies(self, champs, syn_data, pack=None, embed=None, author=None):
        if embed is None:
            embed = discord.Embed(color=discord.Color.red(),
                            title='Champion Synergies')
            return_single = False
        else:
            return_single = True
        if len(champs) > 5:
            raise MODOKError('No Synergy team can be greater than 5 champs')
        effectsused = defaultdict(list)
        champ_set = {champ.full_name for champ in champs}
        activated = {}
        for champ in champs:
            champ_synergies = syn_data['SynExport'][champ.full_name]
            for lookup, data in champ_synergies.items():
                trigger_in_tag = False
                if champ.star != data['stars']:
                    continue
                for trigger in data['triggers']:
                    if lookup in activated:
                        continue
                    if trigger.startswith('#'):
                        for trig_champ in champs:
                            if champ == trig_champ:
                                continue
                            if trigger in trig_champ.all_tags:
                                trigger_in_tag = True
                                break
                    if trigger in champ_set or trigger_in_tag:
                        syneffect = syn_data['SynergyEffects'][data['synergycode']]
                        activated[lookup] = {
                                'champ': champ,
                                'trigger': next(c for c in champs if c.full_name == trigger),
                                'rank': data['rank'],
                                'emoji': syneffect['emoji'],
                                'synergyname': syneffect['synergyname']
                            }
                        if syneffect['is_unique'] == 'TRUE' and data['synergycode'] in effectsused:
                            continue
                        effect = syneffect['rank{}'.format(data['rank'])]
                        effectsused[data['synergycode']].append(effect)

        desc= []
        try:
            embed.description = ''.join(c.collectoremoji for c in champs)
        except:
            print('Collector Emoji not found')
        for k, v in effectsused.items():
            syn_effect = syn_data['SynergyEffects'][k]
            array_sum = [sum(row) for row in iter_rows(v, True)]
            txt = syn_effect['text'].format(*array_sum)
            if embed is not None:
                embed.add_field(name=syn_effect['synergyname'],
                        value=txt, inline=False)
                if author is None:
                    embed.set_footer(text='CollectorDevTeam', icon_url=COLLECTOR_ICON)
                else:
                    embed.set_footer(text='Requested by {}'.format(author.display_name), icon_url=author.avatar_url)
            else:
                desc.append('{}\n{}\n'.format(syn_effect['synergyname'], txt))
        pack.append(embed)
        arrows = '\u2192 \u21d2 \u21a6 <:collectarrow:422077803937267713>'.split()
        sum_txt = '{0[champ].terse_star_str}{0[champ].collectoremoji} ' \
                + '{1} ' \
                + '{0[trigger].terse_star_str}{0[trigger].collectoremoji} ' \
                + '\u2503 Level {0[rank]}'
                #+ '\u2503 {0[synergyname]} Level {0[rank]}'
                #+ '<:collectarrow:422077803937267713> \u21e8 \u2192 \U0001f86a \U0001f87a' \
                #+ 'LVL{0[rank]} {0[emoji]}'
        sum_field = defaultdict(list)
        for v in activated.values():
            arrow = arrows[min(v['champ'].debug, len(arrows)-1)]
            sum_field[v['synergyname']].append(sum_txt.format(v, arrow))
        if return_single:
            pack.append(embed)
            return pack
        else:
            # pages = [embed]
            embed = discord.Embed(color=discord.Color.red(),
                    title='Champion Synergies',
                    description='**Synergy Breakdown**')
            if author is None:
                embed.set_footer(text='CollectorDevTeam', icon_url=COLLECTOR_ICON)
            else:
                embed.set_footer(text='Requested by {}'.format(author.display_name), icon_url=author.avatar_url)

            for syn, lines in sum_field.items():
                embed.add_field(name=syn, value='\n'.join(lines), inline=False)

            #embed.add_field(name='Synergy Breakdown', value='\n'.join(sum_field))
            pack.append(embed)
            return pack

    async def gs_to_json(self, head_url=None, body_url=None, foldername=None, filename=None, groupby_value=None):
        if head_url is not None:
            async with aiohttp.get(head_url) as response:
                try:
                    header_json = await response.json()
                except:
                    print('No header data found.')
                    return
            header_values = header_json['values']

        async with aiohttp.get(body_url) as response:
            try:
                body_json = await response.json()
            except:
                print('No data found.')
                return
        body_values = body_json['values']

        output_dict = {}
        if head_url is not None:
            if groupby_value is None:
                groupby_value = 0
            grouped_by = header_values[0][groupby_value]
            for row in body_values:
                dict_zip = dict(zip(header_values[0],row))
                groupby = row[groupby_value]
                output_dict.update({groupby:dict_zip})
        else:
            output_dict =body_values

        if foldername is not None and filename is not None:
            if not os.path.exists(self.shell_json.format(foldername, filename)):
                if not os.path.exists(self.data_dir.format(foldername)):
                    os.makedirs(self.data_dir.format(foldername))
                dataIO.save_json(self.shell_json.format(foldername, filename), output_dict)
            dataIO.save_json(self.shell_json.format(foldername,filename),output_dict)

            # # Uncomment to debug
            # if champ.debug:
            #     await self.bot.upload(self.shell_json.format(foldername,filename))


        return output_dict

    @commands.command(hidden=True)
    async def dump_sigs(self):
        #await self.update_local()
        sdata = dataIO.load_json(local_files['signature'])
        dump = {}
        for c, champ_class in enumerate(self.champions.values()):
            #if c < 75 or c > 90:
                #continue
            champ = champ_class()
            item = {'name': champ.full_name, 'sig_data': []}
            for i in range(1, 100):
                champ.update_attrs({'sig': i})
                try:
                    title, desc, sig_calcs = await champ.process_sig_description(sdata, quiet=True)
                except (KeyError, IndexError):
                    print("Skipping ", champ.full_name)
                    break
                if sig_calcs is None:
                    break
                if i == 1:
                    item['title'] = title
                    item['description'] = desc
                    item['star_rank'] = champ.star_str
                item['sig_data'].append(sig_calcs)
            if not item['sig_data']:
                continue
            dump[champ.mattkraftid] = item
            print(champ.full_name)
        with open("sig_data_4star.json", encoding='utf-8', mode="w") as fp:
            json.dump(dump, fp, indent='\t', sort_keys=True)
        await self.bot.say('Hopefully dumped')

    @commands.command(hidden=True)
    async def json_sig(self, *, champ : ChampConverterSig):
        if champ.star != 4 or champ.rank != 5:
            await self.bot.say('This function only checks 4* rank5 champs')
            return
        jfile = dataIO.load_json("sig_data_4star.json")
        title, desc, sig_calcs = await champ.process_sig_description(quiet=True)
        jsig = jfile[champ.mattkraftid]
        em = discord.Embed(title='Check for {}'.format(champ.full_name))
        em.add_field(name=jsig['title'],
                value=jsig['description'].format(d=jsig['sig_data'][champ.sig-1]))
        await self.bot.say(embed=em)
        assert title == jsig['title']
        assert desc == jsig['description']
        assert sig_calcs == jsig['sig_data'][champ.sig-1]

    @commands.command(hidden=True)
    async def gs_sig(self):
        await self.update_local()
        gkey = '1kNvLfeWSCim8liXn6t0ksMAy5ArZL5Pzx4hhmLqjukg'
        gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
        gsdata = GSExport(gc, gkey)
        struct = await gsdata.retrieve_data()
        sigs = load_kabam_json(kabam_bcg_stat_en)
        for key in struct.keys():
            champ_class = self.champions.get(key.lower(), None)
            if champ_class is None:
                continue
            struct[key]['kabam_text'] = champ_class.get_kabam_sig_text(
                    champ_class, sigs=sigs,
                    champ_exceptions=struct['kabam_key_override'])
        with open("data/mcoc/gs_json_test.json", encoding='utf-8', mode='w') as fp:
            json.dump(struct, fp, indent='  ', sort_keys=True)
        await self.bot.upload("data/mcoc/gs_json_test.json")

    @champ.command(pass_context=True, name='use', aliases=('howto',))
    async def champ_use(self, ctx, *, champ : ChampConverter):
        '''How to Fight With videos by MCOC Community'''
        released = await self.check_release(ctx, champ)
        if released:
            em = discord.Embed(color=champ.class_color, title='How-To-Use: '+champ.full_name, url='https://goo.gl/forms/VXSQ1z40H4Knia0t2')
            await self.bot.say(embed=em)
            if champ.infovideo != '':
                await self.bot.say(champ.infovideo)
                # await self.bot.say(xref['infovideo'])
            else:
                await self.bot.say('I got nothing. Send the CollectorDevTeam a good video.\nClick the blue text for a survey link.')


    @champ.command(pass_context=True, name='info', aliases=('infopage',))
    async def champ_info(self, ctx, *, champ : ChampConverterDebug):
        '''Champion Spotlight link'''
        # xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)
        em = discord.Embed(color=champ.class_color, title='Champ Info', url=SPOTLIGHT_SURVEY)
        em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
        if champ.infopage == 'none':
            em.add_field(name='Kabam Spotlight', value='No URL found')
        else:
            em.add_field(name='Kabam Spotlight', value=champ.infopage)
        em.add_field(name='Auntm.ai Link', value='https://auntm.ai/champions/{0.mattkraftid}/tier/{0.star}'.format(champ))

        em.add_field(name='Shortcode', value=champ.short)
        em.set_footer(text='MCOC Website', icon_url=KABAM_ICON)
        em.set_thumbnail(url=champ.get_avatar())
        await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='abilities')
    async def champ_abilities(self, ctx,  *, champ: ChampConverterDebug):
        '''Champion Abilities'''
        # imageid='4-{}-5'.format(champ.mattkraftid)
        released = await self.check_release(ctx, champ)
        if released:
            imageurl='{}/images/abilities/4-{}-5.png'.format(remote_data_basepath, champ.mattkraftid)
            em = discord.Embed(color=champ.class_color, title='Champ Abilities', url=SPOTLIGHT_SURVEY)
            em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
            em.set_image(url=imageurl)
            if champ.abilities is not None:
                em.add_field(name='Named Abilities', value=champ.abilities.title())
            if champ.extended_abilities is not None:
                em.add_field(name='Extended Abilities', value=champ.extended_abilities.title())
            if champ.counters is not None:
                em.add_field(name='{} can counter these abilities'.format(champ.full_name), value=champ.counters.title())
            if champ.hashtags is not None:
                em.add_field(name='Hashtags', value=champ.hashtags)
            em.add_field(name='Shortcode', value=champ.short)
            em.set_footer(text='CollectorDevTeam | Requested by {}'.format(ctx.message.author.display_name), icon_url=COLLECTOR_ICON)
            em.set_thumbnail(url=champ.get_featured())
            await self.bot.say(embed=em)
        else:
            await self.champ_embargo(ctx, champ)



    @champ.command(pass_context=True, name='specials', aliases=['special',])
    async def champ_specials(self, ctx, champ : ChampConverter):
        '''Special Attack Descritpion'''
        try:
            specials = champ.get_special_attacks()
            em = discord.Embed(color=champ.class_color, title='Champion Special Attacks')
            em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
            em.add_field(name=specials[0], value=specials[3])
            em.add_field(name=specials[1], value=specials[4])
            em.add_field(name=specials[2], value=specials[5])
            em.set_thumbnail(url=champ.get_avatar())
            em.add_field(name='Shortcode', value=champ.short)
            em.set_footer(text='MCOC Game Files', icon_url=KABAM_ICON)
            await self.bot.say(embed=em)
        except:
            await self.bot.say('Special Attack not found')

    @champ.command(pass_context=True, name='prestige')
    async def champ_prestige(self, ctx, *, champs : ChampConverterMult):
        '''Champion(s) Prestige'''
        pch = [c for c in champs if c.has_prestige]
        numerator = 0
        spch = sorted(pch, key=attrgetter('prestige'), reverse=True)
        denom = min(len(spch), 5)
        numerator = sum(spch[i].prestige for i in range(denom))
        if denom != 0:
            em = discord.Embed(color=discord.Color.magenta(),
                    title='Prestige: {}'.format(numerator/denom),
                    url='https://auntm.ai',
                    description='\n'.join(c.verbose_prestige_str for c in spch)
                )
            em.set_footer(text='https://auntm.ai | CollectorVerse',
                    icon_url=AUNTMAI)
            await self.bot.say(embed=em)
        else:
            em = discord.Embed(color=discord.Color.magenta(),
                    title='Not Enough Data',
                    url='https://auntm.ai',
                    description='Summoner, your request would result in a division by zero which would cause a black hole and consume the multiverse.'
                )
            em.set_footer(text='https://auntm.ai | CollectorVerse',
                    icon_url=AUNTMAI)
            await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='aliases', aliases=('alias',))
    async def champ_aliases(self, ctx, *args):
        '''Champion Aliases'''
        em = discord.Embed(color=discord.Color.teal(), title='Champion Aliases')
        champs_matched = set()
        for arg in args:
            arg = arg.lower()
            if (arg.startswith("'") and arg.endswith("'")) or \
                    (arg.startswith('"') and arg.endswith('"')):
                champs = await self.search_champions(arg[1:-1])
            elif '*' in arg:
                champs = await self.search_champions('.*'.join(re.split(r'\\?\*', arg)))
            else:
                champs = await self.search_champions('.*{}.*'.format(arg))
            for champ in champs:
                if champ.mattkraftid not in champs_matched:
                    em.add_field(name=champ.full_name, value=champ.get_aliases())
                    champs_matched.add(champ.mattkraftid)
        await self.bot.say(embed=em)


    @commands.command(hidden=True)
    async def tst(self, key):
        files = {'bio': (kabam_bio, 'ID_CHARACTER_BIOS_', 'mcocjson'),
                 'sig': (kabam_bcg_stat_en, 'ID_UI_STAT_', 'mcocsig')}
        ignore_champs = ('DRONE', 'SYMBIOD')
        if key not in files:
            await self.bot.say('Accepted Key values:\n\t' + '\n\t'.join(files.keys()))
            return
        data = load_kabam_json(files[key][0])
        no_mcocjson = []
        no_kabam_key = []
        data_keys = {k for k in data.keys() if k.startswith(files[key][1])}
        ignore_keys = set()
        for champ in ignore_champs:
            ignore_keys.update({k for k in data_keys if k.find(champ) != -1})
        data_keys -= ignore_keys
        print(ignore_keys)
        for champ in self.champs:
            if not getattr(champ, files[key][2], None):
                no_mcocjson.append(champ.full_name)
                continue
            kabam_key = files[key][1] + getattr(champ, files[key][2])
            champ_keys = {k for k in data.keys() if k.startswith(kabam_key)}
            if not champ_keys:
                no_kabam_key.append(champ.full_name)
            else:
                data_keys -= champ_keys
        if no_mcocjson:
            await self.bot.say('Could not find mcocjson alias for champs:\n\t' + ', '.join(no_mcocjson))
        if no_kabam_key:
            await self.bot.say('Could not find Kabam key for champs:\n\t' + ', '.join(no_kabam_key))
        if data_keys:
            #print(data_keys, len(data_keys))
            if len(data_keys) > 20:
                dump = {k for k in data_keys if k.endswith('TITLE')}
            else:
                dump = data_keys
            await self.bot.say('Residual keys:\n\t' + '\n\t'.join(dump))
        await self.bot.say('Done')

    # @commands.has_any_role('DataDonors','CollectorDevTeam','CollectorSupportTeam','CollectorPartners')
    @commands.group(pass_context=True, aliases=['donate',])
    async def submit(self, ctx):
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @submit.command(pass_context=True, name='stats')
    async def submit_stats(self, ctx, champ: ChampConverter = None, *, stats: str = None):
        '''Submit Champion Stats and or Images
        valid keys: hp, atk, cr, cd, blockpen, critresist, armorpen, armor, bp'''
        if stats is not None:
            stats = stats.lower()
        attachments = ctx.message.attachments
        author = ctx.message.author
        server = ctx.message.server
        cdt_stats = self.bot.get_channel('391358016328302593')

        data = discord.Embed(color=author.color, title='Submit Stats')
        data.set_footer(text='Submitted by {} on {} [{}]'.format(author.display_name, server.name, server.id),
                        icon_url=author.avatar_url)
        if champ is None:
            data.title='Submit Stats Help'
            data.set_author(name='``/submit stats <champ> <stats>``')
            data.description = 'Include a champion.  Star and Rank required\n' \
                               '    i.e:\n' \
                               '    4\*blackboltr5 == 4★ Black Bolt r5 \n' \
                               '    6\*blackboltr2 == 6★ Black Bolt r2 \n'\
                               'Minimum stats submissions include Health & Attack.\n' \
                               'However, we strongly encourage you to submit **all** champion base stats.\n' \
                               '1. Select Champion\n' \
                               '2. Select Info\n' \
                               '3. Tap the ``attributes`` information panel\n' \
                               '\n' \
                               'Image attachments will be uploaded to CDT Server.\n' \
                               '\n' \
                               'Alternative:\n' \
                               '[Submit Stats via Google Form](https://goo.gl/forms/ZgJG97KOpeSsQ2092)'
            data.set_image(
                url='https://cdn.discordapp.com/attachments/278246904620646410/550010804880277554/unknown.png')
            await self.bot.say(embed=data)
            return
        elif champ is not None:
            data.set_thumbnail(url=champ.get_featured())
        if stats is None and len(ctx.message.attachments) > 0:
            if len(attachments) > 2:
                for i in attachments:
                    data.add_field(name='Image submission', value=attachments[i]['url'])
            elif len(attachments) == 1:
                data.set_image(url=attachments[0]['url'])
            await self.bot.send_message(cdt_stats, embed=data)
            return
        elif stats is None:
            data.title='Submit Stats Help'
            data.set_author(name='``/submit stats <champ> <stats>``')
            data.description = 'Minimum stats submissions include Health & Attack.\n' \
                               'However, we strongly encourage you to submit **all** champion base stats.\n' \
                               '1. Select Champion\n' \
                               '2. Select Info\n' \
                               '3. Tap the ``attributes`` information panel' \
                               '\n' \
                               'Image attachments will be uploaded to CDT Server.' \
                               '\n' \
                               'Alternative:\n' \
                               '[Submit Stats via Google Form](https://goo.gl/forms/ZgJG97KOpeSsQ2092)'

            data.set_image(
                url='https://cdn.discordapp.com/attachments/278246904620646410/550010804880277554/unknown.png')
            data.add_field(name='Example format',
                           value='``/submit stats 5*sentry hp 12345 atk 1234 cr 123 cd 123 armor 123 bp 1234``')
            data.add_field(name='Submission Error', value='No information included.\n Try harder next time.')
            await self.bot.say(embed=data)
            # await self.bot.say('Submit Stats debug: Did not match stats')
            return
        else:
            default = {
                'hp': {'v': 0, 'title': 'Health'},# Health
                'atk': {'v': 0, 'title': 'Attack'},# Attack
                'cr': {'v': 0, 'title': 'Critical Rate'},# Critical Rate
                'cd': {'v': 0, 'title': 'Critical Damage'},# Critical Damage
                'blockpen': {'v': 0, 'title': 'Block Penetration'},# Blcok Proficiency
                'critresist': {'v': 0, 'title': 'Critical Resistance'},# Critical Resistance
                'armorpen':  {'v': 0, 'title': 'Armor Penetration'},# Armor Penetration
                'armor':  {'v': 0, 'title': 'Armor'},# Armor
                'bp':  {'v': 0, 'title': 'Block Proficiency'},# Block Proficiency
            }
            # https://regex101.com/r/um4NsT/4 thanks Wchou
            regex = r'((h|hp|health)(\s+)?(?P<hp>\d{1,6}))?(\s+)?' \
                    r'((attack|atk)(\s+)?(?P<atk>\d{1,4}))?(\s+)?' \
                    r'((cr|critrate)(\s+)?(?P<cr>\d{1,4}))?(\s+)?' \
                    r'((cd|critdamage)(\s+)?(?P<cd>\d{1,4}))?(\s+)?' \
                    r'((armorp|apen|armorpen)(\s+)?(?P<armorpen>\d{1,4}))?(\s+)?' \
                    r'((blockpen|bpen)(\s+)(?P<blockpen>\d{1,4}))?(\s+)?' \
                    r'((critresist|cres|crr)(\s+)?(?P<critresist>\d{1,4}))?(\s+)?' \
                    r'((ar|armor)(\s+)?(?P<armor>\d{1,4}))?(\s)?' \
                    r'((bp|blockprof)(\s+)?(?P<bp>\d{1,5}))?(\s)?'
            r = re.search(regex, stats)
            matches = r.groupdict()

            if r is None or matches is None or matches.keys() is None:
                data.description = 'Minimum stats submissions include Health & Attack.\n' \
                                   'However, we strongly encourage you to submit **all** champion base stats.\n' \
                                   '1. Select Champion\n' \
                                   '2. Select Info\n' \
                                   '3. Tap the ``attributes`` information panel' \
                                   '\n' \
                                   'Image attachments will be uploaded to CDT Server.'
                data.set_image(url='https://cdn.discordapp.com/attachments/278246904620646410/550010804880277554/unknown.png')
                data.add_field(name='Submission Error', value='Could not decipher submission.\n Try harder next time.')
                message = await self.bot.say(embed=data)
                # await self.bot.say('Submit Stats debug: Did not match stats')
                return
            elif 'hp' not in matches.keys() and 'atk' not in matches.keys():
                data.description = 'Minimum stats submissions include Health & Attack.\n' \
                                   'However, we strongly encourage you to submit **all** champion base stats.\n' \
                                   '1. Select Champion\n' \
                                   '2. Select Info\n' \
                                   '3. Tap the ``attributes`` information panel\n' \
                                   '\n' \
                                   'Image attachments will be uploaded to CDT Server.'
                data.set_image(url='https://cdn.discordapp.com/attachments/278246904620646410/550010804880277554/unknown.png')
                message = await self.bot.say(embed=data)
                return
            else:
                for k in matches.keys():
                    if matches[k] is not None:
                        default[k]['v'] = int(matches[k])


            saypackage = 'Submission registered.\nChampion: ' + champ.verbose_str

            for k in ('hp', 'atk', 'cr', 'cd','blockpen', 'critresist', 'armorpen', 'armor','bp'):
                saypackage += '\n{} : {}'.format(default[k]['title'], default[k]['v'])

            if len(attachments) > 0:
                saypackage += '\nAttachments:'
                for a in attachments:
                    saypackage += '\{}'.format(a.url)

            answer, confirmation = await PagesMenu.confirm(self, ctx, saypackage)
            data.description = saypackage
            # data.author(name=ctx.message.author.display_name, icon_url=ctx.message.author.avatar_url)

            if answer is False:
                await self.bot.say('Submission canceled.')
                await self.bot.delete_message(confirmation)
            elif answer is True:
                if default['hp']['v'] == 0 or default['atk']['v'] == 0:
                    data.add_field(name='Submission Error', value='Minimum required submission includes Health & Attack. \nPreferred submissions include all base stats.\n\nPlease try harder.')
                    data.add_field(name='Example format',
                                   value='``/submit stats {} hp 12345 atk 1234 cr 123 cd 123 armor 123 bp 1234``'
                                   .format(champ.unique))
                    data.set_image(
                        url='https://cdn.discordapp.com/attachments/278246904620646410/550010804880277554/unknown.png')
                    data.set_footer(
                        text='Submission Attempted by {} on {} [{}]'.format(author.display_name, server.name, server.id),
                        icon_url=author.avatar_url)
                    message = await self.bot.say(embed=data)
                    await self.bot.delete_message(confirmation)
                    return
                GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE'
                message2 = await self.bot.say(embed=discord.Embed(color=author.color, title='Submission in progress.'))
                level = champ.rank*10
                if champ.star > 4:
                    level += 15
                package = [[str(ctx.message.timestamp), author.name, champ.full_name, champ.star, champ.rank, level,
                            str(default['hp']['v']), str(default['atk']['v']), str(default['cr']['v']), str(default['cd']['v']),
                            str(default['armorpen']['v']), str(default['blockpen']['v']), str(default['critresist']['v']),
                            str(default['armor']['v']), str(default['bp']['v']), author.id]]
                # check = await self.bot.say('Debug - no stats submissions accepted currently.')
                check = await self._process_submission(package=package, GKEY=GKEY, sheet='submit_stats')
                if check:
                    data.set_footer(
                        text='Submission Registered by {} on {} [{}]'.format(author.display_name, server.name, server.id),
                        icon_url=author.avatar_url)
                    await self.bot.delete_message(message2)
                    if cdt_stats is not None:
                        await self.bot.send_message(cdt_stats, embed=data)
                        await self.bot.say(embed=data)
                        if len(ctx.message.attachments) > 0:
                            for a in ctx.message.attachments:
                                await self.bot.send_message(cdt_stats, a.url)
                else:
                    await self.bot.edit_message(message2, 'Submission failed.')
                await self.bot.delete_message(confirmation)
            else:
                await self.bot.say('Ambiguous response.  Submission canceled')
                await self.bot.delete_message(confirmation)


    @submit.command(pass_context=True, name='prestige')
    async def submit_prestige(self, ctx, champ: ChampConverter = None, observation: int = None):
        '''Submit Champion Prestige + Images'''
        author = ctx.message.author
        server = ctx.message.server

        cdt_prestige = self.bot.get_channel('391358076219031553')
        data = discord.Embed(color=author.color, title='Submit Prestige')
        if champ is None or observation is None:
            pages = []
            data.title = 'Submit Prestige From Your Roster'
            data.set_footer(text='{} on {} [{}]'.format(author.display_name, server.name, server.id),
                            icon_url=author.avatar_url)
            data.description = 'In order to submit prestige, the following is required:\n' \
                             '**Masteries must be removed**\n' \
                             'Champions must be at the maximum level for a given rank.\n' \
                             'i.e.\n' \
                             '```4★ r1 at level 10  |  5★ r1 at level 15\n' \
                             '4★ r2 at level 20  |  5★ r2 at level 25\n' \
                             '4★ r3 at level 30  |  5★ r3 at level 35\n' \
                             '4★ r4 at level 40  |  5★ r4 at level 45\n' \
                             '4★ r5 at level 50  |  5★ r5 at level 55\n```'
            data.add_field(name='Attach Screenshots', value='Images may be attached to this command.\n'
                                                            'Attached images will cross-post to the CollectorDevTeam server for inspection.')
            data.add_field(name='Example', value='```/submit prestige 5*x23r4s20 5871```\n')
            data.set_image(url='https://cdn.discordapp.com/attachments/390255698405228544/550783184430825482/unknown.png')
            pages.append(data)
            data2 = discord.Embed(color=author.color, title='Submit Prestige From Alliance Openings')
            data2.set_footer(text='{} on {} [{}]'.format(author.display_name, server.name, server.id),
                            icon_url=author.avatar_url)
            data2.description = 'Alliance-mate Opening Observations\n' \
                                'You can report prestige from Alliance openings.\n ' \
                                'Alliance openings are GREEN text in your Alliance feed.\n ' \
                                'Click on the left-hand side of the item, on the champion portrait.\n ' \
                                'The Champion Prestige is reported on this information screen.\n ' \
                               'Champions must be at the maximum level for a given rank.\n' \
                               'i.e.\n' \
                               '```4★ r1 at level 10  |  5★ r1 at level 15\n' \
                               '4★ r2 at level 20  |  5★ r2 at level 25\n' \
                               '4★ r3 at level 30  |  5★ r3 at level 35\n' \
                               '4★ r4 at level 40  |  5★ r4 at level 45\n' \
                               '4★ r5 at level 50  |  5★ r5 at level 55\n```'
            data2.add_field(name='Attach Screenshots', value='Images may be attached to this command.\n' \
                                                            'Attached images will cross-post to the CollectorDevTeam server for inspection.')
            data2.add_field(name='Example', value='```/submit prestige 5*x23r4s20 5871```\n')

            data2.set_image(url='https://media.discordapp.net/attachments/390255698405228544/550782742141599798/unknown.png')
            pages.append(data2)
            menu = PagesMenu(self.bot, timeout=120, delete_onX=True, add_pageof=True)
            await menu.menu_start(pages)
            return
        else:
            data.set_footer(text='Submitted by {} on {} [{}]'.format(author.display_name, server.name, server.id),
                            icon_url=author.avatar_url)
            data.set_thumbnail(url=champ.get_avatar())
            question = 'Submission registered.\nChampion: {0.verbose_str}\nPrestige: {1}'\
                .format(champ, observation)
            data.description = question
            answer, confirmation = await PagesMenu.confirm(self, ctx, question)
            if len(ctx.message.attachments) == 1:
                data.set_image(url=ctx.message.attachments[0]['url'])
            elif len(ctx.message.attachments) > 1:
                for attachment in ctx.message.attachements:
                    data.set_image(url=attachment['url'])
                    await self.bot.send_message('{}\n{}'.format(champ.verbose_str, attachment['url']))
            if answer is False:
                data.add_field(name='Status', value='Cancelled by {}'.format(author.display_name))
                await self.bot.delete_message(confirmation)
                await self.bot.say(emebed=data)
                return
            elif answer is True:
                await self.bot.delete_message(confirmation)
                message = await self.bot.say(embed=data)
                GKEY = '1HXMN7PseaWSvWpNJ3igUkV_VT-w4_7-tqNY7kSk0xoc'
                message2 = await self.bot.say('Submission in progress.')
                package = [['{}'.format(champ.mattkraftid), champ.sig, observation, champ.star, champ.rank, champ.max_lvl, author.name, author.id, str(ctx.message.timestamp)]]
                check = await self._process_submission(package=package, GKEY=GKEY, sheet='collector_submit')
                await self.bot.send_message(cdt_prestige, embed=data)
                if check:
                    data.add_field(name='Status', value='Submission complete.')
                else:
                    data.add_field(name='Status', value='Submission failed.')
                await self.bot.delete_message(message2)
                await self.bot.edit_message(message, embed=data)


    @submit.command(pass_context=True, name='sigs', aliases=('signatures', 'sig',))
    async def submit_sigs(self, ctx, champ: ChampConverter):
        author = ctx.message.author
        server = ctx.message.server
        cdt_sigs = self.bot.get_channel('391358050918727692')
        data = discord.Embed(color=author.color, title='Submit Signatures')
        data.set_thumbnail(url=champ.get_avatar())
        data.set_footer(text='Submitted by {} on {} [{}]'.format(author.display_name, server.name, server.id),
                        icon_url=author.avatar_url)
        data.description = '{} rank {}'.format(champ.full_name, champ.rank)
        attachements = []
        if len(ctx.message.attachments) == 0:
            data.description = 'Champion Signature abilities must be manually coded.\n ' \
                               'Resubmit this command with any number of image attachments.\n' \
                               'If you are submitting a batch of images, every 5 levels of ' \
                               'signature ability are more than sufficient.\n\n' \
                               'Be sure to specify the champion **rank**.'
            await self.bot.say(embed=data)
            return
        elif len(ctx.message.attachments) == 1:
            data.set_image(url=ctx.message.attachments[0]['url'])
        else:
            attachements = ctx.message.attachments

        saypackage = 'Do you want to submit image attachements for\n{}'.format(champ.verbose_str)
        answer, confirmation = await PagesMenu.confirm(self, ctx, saypackage)
        if answer:
            await self.bot.say(embed=data)
            await self.bot.delete_message(confirmation)
            await self.bot.send_message(cdt_sigs, embed=data)
            if len(attachements) > 0:
                for i in attachements:
                    await self.bot.send_message(cdt_sigs, i['url'])
                await self.bot.send_message(cdt_sigs, 'Final submission for {}'.format(champ.verbose_str))

    # # @submit.command(pass_context=True, name='defenders', aliases=['awd'], hidden=true)
    # # async def submit_awd(self, ctx, target_user: str, *, champs : ChampConverterMult):
    # #
    # #     message_text = ['Alliance War Defender Registration','Target User: ' + target_user]
    # #     author = ctx.message.author
    # #     now = str(ctx.message.timestamp)
    # #     if len(champs) > 5:
    # #         await self.bot.say('Defense Error: No more than 5 Defenders permitted.')
    # #         return
    # #     for champ in champs:
    # #         message_text.append('{0.star_name_str}'.format(champ))
    # #
    # #     print('package built')
    # #     message_text.append('Press OK to confirm.')
    # #     message = await self.bot.say('\n'.join(message_text))
    # #     await self.bot.add_reaction(message, '❌')
    # #     await self.bot.add_reaction(message, '🆗')
    # #     react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
    # #
    #
    #
    #     if react is not None:
    #         if react.reaction.emoji == '❌':
    #             await self.bot.say('Submission canceled.')
    #         elif react.reaction.emoji == '🆗':
    #             # GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE'
    #             GKEY = '19yPuvT2Vld81RJlp4XD33kSEM-fsW8co5dN9uJkZ908'
    #             message2 = await self.bot.say('Submission in progress.')
    #
    #             for champ in champs:
    #                 package = [now, author.name, author.id, target_user, champ.unique]
    #                 check = await self._process_submission(package=package, GKEY=GKEY, sheet='collector_submit')
    #             if check:
    #                 await self.bot.edit_message(message2, 'Submission complete.')
    #                 async with aiohttp.ClientSession() as s:
    #                     await asyncio.sleep(10)
    #                     # await self.cache_remote_file('alliancewardefenders', s, force_cache=True, verbose=True)
    #                     await self.bot.edit_message(message2, 'Submission complete.\nAlliance War Defenders refreshed.')
    #             else:
    #                 await self.bot.edit_message(message2, 'Submission failed.')
    #     else:
    #         await self.bot.say('Ambiguous response.  Submission canceled')


    @submit.command(pass_context=True, name='duel', aliases=['duels','target'])
    async def submit_duel_target(self, ctx, champ : ChampConverter, observation, pi:int = 0):
        # guild = await self.check_guild(ctx)
        cdt_duels = self.bot.get_channel('404046914057797652')
        server = ctx.message.server
        author = ctx.message.author
        data = discord.Embed(color=author.color, title='Submit Duel Targets')
        data.set_thumbnail(url=champ.get_featured())
        data.description = 'Duel Target registered.\nChampion: {0.star_name_str}\nTarget: {1}\nPress OK to confirm.'.format(
                champ, observation)
        data.set_footer(text='Submitted by {} on {} [{}]'
                        .format(author.display_name, server.name, server.id),
                        icon_url=author.avatar_url)
        message = await self.bot.say(embed=data)
        await self.bot.add_reaction(message, '❌')
        await self.bot.add_reaction(message, '🆗')
        react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
        if react is not None:
            if react.reaction.emoji == '❌':
                await self.bot.say('Submission canceled.')
            elif react.reaction.emoji == '🆗':
                # GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE'
                GKEY = '1FZdJPB8sayzrXkE3F2z3b1VzFsNDhh-_Ukl10OXRN6Q'
                message2 = await self.bot.say(embed=discord.Embed(color=author.color, title='Submission in progress.'))
                author = ctx.message.author
                star = '{0.star}{0.star_char}'.format(champ)
                if pi == 0:
                    if champ.has_prestige:
                        pi=champ.prestige
                now = str(ctx.message.timestamp)
                package = [[now, author.name, star, champ.full_name, champ.rank, champ.max_lvl, pi, observation, author.id]]
                print('package built')
                check = await self._process_submission(package=package, GKEY=GKEY, sheet='collector_submit')
                if check:
                    await self.bot.delete_message(message2)
                    data.add_field(name='Status', value='Submission Complete')
                    await self.bot.edit_message(message, embed=data)
                    data.add_field(name='Duel Target System', value='Refreshed')
                    async with aiohttp.ClientSession() as s:
                        await asyncio.sleep(20)
                        await self.cache_remote_file('duelist', s, force_cache=True, verbose=True)
                        await self.bot.edit_message(message, embed=data)
                        await self.bot.send_message(cdt_duels, embed=data)
                else:
                    await self.bot.delete_message(message2)
                    data.add_field(name='Status', value='Submission failed')
                    await self.bot.edit_message(message, embed=data)
                    await self.bot.send_message(cdt_duels, embed=data)

        else:
            data.add_field(name='Ambiguous response', value='Submission cancelled')
            await self.bot.edit_message(message, embed=data)

    # @commands.has_any_role('DataDonors','CollectorDevTeam','CollectorSupportTeam','CollectorPartners')
    @submit.command(pass_context=True, name='defkill', aliases=['defko',])
    async def submit_awkill(self, ctx, champ : ChampConverter, node:int, ko: int):
        author = ctx.message.author
        message = await self.bot.say('Defender Kill registered.\n'
                                     'Champion: {0.verbose_str}\n'
                                     'AW Node: {1}\nKills: {2}\n'
                                     'Press OK to confirm.'.format(champ, node, ko))
        await self.bot.add_reaction(message, '❌')
        await self.bot.add_reaction(message, '🆗')
        react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
        if react is not None:
            if react.reaction.emoji == '❌':
                await self.bot.say('Submission canceled.')
            elif react.reaction.emoji == '🆗':
                GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE' #Collector Submissions
                message2 = await self.bot.say(embed=discord.Embed(color=author.color, title='Submission in progress.'))
                author = ctx.message.author
                now = str(ctx.message.timestamp)
                package = [[now, author.name, author.id, champ.unique, node, ko]]
                print('package built')
                check = await self._process_submission(package=package, GKEY=GKEY, sheet='defender_kos')
                if check:
                    await self.bot.edit_message(message2,
                                                embed=discord.Embed(color=author.color, title='Submission Status', description='Submission complete'))
                else:
                    await self.bot.edit_message(message2,
                                                embed=discord.Embed(color=author.color, title='Submission Status', description='Submission failed'))
            GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE' # Collector Submissions
            message2 = await self.bot.say(embed=discord.Embed(color=author.color, title='Submission Status', description='Ambiguous response.\nSubmission cancelled'))
            now = str(ctx.message.timestamp)
            package = [[now, author.name, author.id, champ.unique, node, ko]]
            print('package built')
            check = await self._process_submission(package=package, GKEY=GKEY, sheet='defender_kos')
            if check:
                await self.bot.edit_message(message2,
                                            embed=discord.Embed(color=author.color, title='Submission Status',
                                                                description='Submission complete'))
            else:
                await self.bot.edit_message(message2,
                                            embed=discord.Embed(color=author.color, title='Submission Status',
                                                                description='Submission failed'))

    @commands.has_any_role('DataDonors','CollectorDevTeam','CollectorSupportTeam','CollectorPartners')
    @submit.command(pass_context=True, name='100hits', aliases=['50hits',])
    async def submit_100hitchallenge(self, ctx, champ : ChampConverter, hits : int, wintersoldier_hp : int, author : discord.User = None):
        if author is None:
            author = ctx.message.author
        message = await self.bot.say('100 Hit Challenge registered.\nChampion: {0.verbose_str}\nHits: {1}\nWinter Soldier HP: {2}\nPress OK to confirm.'.format(champ, hits, wintersoldier_hp))
        await self.bot.add_reaction(message, '❌')
        await self.bot.add_reaction(message, '🆗')
        react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
        GKEY = '1RoofkyYgFu6XOypoe_IPVHivvToEuLL2Vqv1KDQLGlA' #100 hit challenge
        SHEETKEY = 'collector_submit'
        pct = round(((547774-wintersoldier_hp)/547774)*100, 4)
        now = str(ctx.message.timestamp)
        package = [[author.name, champ.unique, champ.full_name, champ.star, champ.rank, wintersoldier_hp, hits, pct, now]]
        print('package built')
        if react is not None:
            if react.reaction.emoji == '❌':
                await self.bot.say('Submission canceled.')
            elif react.reaction.emoji == '🆗':
                message2 = await self.bot.say('Submission in progress.')
                check = await self._process_submission(package=package, GKEY=GKEY, sheet=SHEETKEY)
                if check:
                    await self.bot.edit_message(message2, 'Submission complete.\nWinter Soldier Damage: {}%'.format(pct))
                else:
                    await self.bot.edit_message(message2, 'Submission failed.')
        else:
            message2 = await self.bot.say('Ambiguous response: Submission in progress.')
            print('package built')
            check = await self._process_submission(package=package, GKEY=GKEY, sheet=SHEETKEY)
            if check:
                await self.bot.edit_message(message2, 'Submission complete.\nWinter Soldier Damage: {}%'.format(pct))
            else:
                await self.bot.edit_message(message2, 'Submission failed.')

    async def check_guild(self, ctx):
        authorized = ['215271081517383682','124984400747167744','378035654736609280','260436844515164160']
        serverid = ctx.message.server.id
        return serverid in authorized

    async def check_collectordevteam(self, ctx):
        author = ctx.message.author
        cdt = self.bot.get_server("215271081517383682")
        cdtdevteam = _get_role(cdt, '390253643330355200')
        kabam = _get_role(cdt, '542109943910629387')
        member = cdt.get_member(author.id)
        if member is None:
            return False
        elif cdtdevteam in member.roles:
            print('{} {} is CollectorDevTeam'.format(member.display_name, member.id))
            return True
        elif kabam in member.roles:
            print('{} {} is KABAM'.format(member.display_name, member.id))
            return True
        print('{} is not authorised for embargoed content.'.format(author.display_name))
        return False

    async def check_release(self, ctx, champ):
        '''Champion Data is under embargo until the Champion Release date'''
        print('initializing release status check')
        try:
            if champ.released is not None:
                rdate = dateParse(champ.released)
                cdt = await self.check_collectordevteam(ctx)
                print('champ.released is a datetime.date object')
                now = datetime.now()
                if rdate <= now:
                    print('rdate <= now')
                    return True
                elif cdt:
                    print('CollectorDevTeam override.')
                    return True
                else:
                    print('rdate > now')
                    await self.champ_embargo(ctx, champ)
                    return False
            else:
                return True
        except ValueError:
            print('dateParse Failure')
            await self.champ_embargo(ctx, champ)
            return False

    async def champ_embargo(self, ctx, champ):
        em=discord.Embed(color=champ.class_color, title='Information Embargo', url=SPOTLIGHT_DATASET)
        em.description = 'Champion information is under KABAM embargo until release date.  \nCheck back on {}'.format(champ.released)
        em.set_author(name=champ.full_name, icon_url=champ.get_avatar())

        em.add_field(name='Shortcode', value=champ.short, inline=True)
        em.set_thumbnail(url=champ.get_featured())
        em.set_footer(text='CollectorDevTeam Dataset', icon_url=COLLECTOR_ICON)
        await self.bot.say(embed=em)



    async def _process_submission(self, package, GKEY, sheet):
        try:
            gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
        except FileNotFoundError:
            await self.bot.say('Cannot find credentials file.  Needs to be located:\n'
                + gapi_service_creds)
            return False
        else:
            sh = gc.open_by_key(key=GKEY, returnas='spreadsheet')
            worksheet = sh.worksheet(property='title', value=sheet)
            worksheet.append_table(start='A1', end=None, values=package, dimension='ROWS', overwrite=False)
            worksheet.sync()
            return True

    # async def _process_submit_prestige(self, ctx, champ, observation):
    #     GKEY = '1HXMN7PseaWSvWpNJ3igUkV_VT-w4_7-tqNY7kSk0xoc'
    #     author = ctx.message.author
    #     level = int(champ.rank)*10
    #     if champ.star == 5:
    #         level += 15
    #     package = [['{}'.format(champ.mattkraftid), champ.sig, observation, champ.star, champ.rank, level, author.name, author.id]]
    #     try:
    #         gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
    #     except FileNotFoundError:
    #         await self.bot.say('Cannot find credentials file.  Needs to be located:\n'
    #         + gapi_service_creds)
    #         return
    #     sh = gc.open_by_key(key=GKEY,returnas='spreadsheet')
    #     worksheet = sh.worksheet(property='title',value='collector_submit')
    #     worksheet.append_table(start='A2',end=None, values=package, dimension='ROWS', overwrite=False)
    #     worksheet.sync()

    @commands.has_any_role('DataDonors','CollectorDevTeam','CollectorSupportTeam','CollectorPartners')
    @commands.group(pass_context=True, hidden=True)
    async def costs(self, ctx):
        guild = await self.check_guild(ctx)
        if not guild:
            await self.bot.say('This server is unauthorized.')
            return
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @costs.command(name='rankup', aliases=['rank',])
    async def cost_rankup(self, ctx, champs : ChampConverterMult):
        counter = 0
        for champ in champs:
            counter += 1
        print('rankup counter: '+str(counter))


def validate_attr(*expected_args):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            for attr in expected_args:
                if getattr(self, attr + '_data', None) is None:
                    raise AttributeError("{} for Champion ".format(attr.capitalize())
                        + "'{}' has not been initialized.".format(self.champ))
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


class Champion:

    base_tags = {'#cr{}'.format(i) for i in range(10, 130, 10)}
    base_tags.update({'#{}star'.format(i) for i in range(1, 6)})
    base_tags.update({'#{}*'.format(i) for i in range(1, 6)})
    base_tags.update({'#awake', }, {'#sig{}'.format(i) for i in range(1, 201)})
    dupe_levels = {2: 1, 3: 8, 4: 20, 5: 20, 6: 20}
    default_stars = {i: {'rank': i+1, 'sig': 99} for i in range(1,5)}
    default_stars[5] = {'rank': 5, 'sig': 200}
    default_stars[6] = {'rank': 1, 'sig': 200}

    sig_raw_per_str = '{:.2%}'
    sig_per_str = '{:.2f} ({:.2%})'

    def __init__(self, attrs=None):
        self.warn_bold_say = partial(warn_bold_say, self.bot)
        if attrs is None:
            attrs = {}
        self.debug = attrs.pop('debug', 0)

        self._star = attrs.pop('star', 4)
        if self._star < 1:
            logger.warn('Star {} for Champ {} is too low.  Setting to 1'.format(
                    self._star, self.full_name))
            self._star = 1
        if self._star > 6:
            logger.warn('Star {} for Champ {} is too high.  Setting to 6'.format(
                    self._star, self.full_name))
            self._star = 6
        self._default = self.default_stars[self._star].copy()

        for k,v in attrs.items():
            if k not in self._default:
                setattr(self, k, v)
        self.tags = set()
        self.update_attrs(attrs)

    def __repr__(self):
        return '{}({})'.format(type(self).__name__.capitalize(), self.attrs_str)

    def __eq__(self, other):
        return self.immutable_id == other.immutable_id \
                and self.rank == other.rank \
                and self.sig == other.sig

    def update_attrs(self, attrs):
        self.tags.difference_update(self.base_tags)
        for k in ('rank', 'sig'):
            if k in attrs:
                setattr(self, '_' + k, attrs[k])
        if self.sig < 0:
            self._sig = 0
        if self.rank < 1:
            self._rank = 1
        if self.star >= 5:
            if self.rank > 5:
                self._rank = 5
            if self.sig > 200:
                self._sig = 200
        elif self.star < 5:
            if self.rank > (self.star + 1):
                self._rank = self.star + 1
            if self.sig > 99:
                self._sig = 99
        self.tags.add('#cr{}'.format(self.chlgr_rating))
        self.tags.add('#{}star'.format(self.star))
        self.tags.add('#{}*'.format(self.star))
        if self.sig != 0:
            self.tags.add('#awake')
        self.tags.add('#sig{}'.format(self.sig))

    def update_default(self, attrs):
        self._default.update(attrs)

    def inc_dupe(self):
        self.update_attrs({'sig': self.sig + self.dupe_levels[self.star]})

    def get_avatar(self):
        image = '{}images/portraits/{}.png'.format(remote_data_basepath, self.mattkraftid)
        logger.debug(image)
        return image

    def get_featured(self):
        image = '{}images/featured/{}.png'.format(
                    remote_data_basepath, self.mattkraftid)
        logger.debug(image)
        return image

    async def get_bio(self):
        sgd = cogs.mcocTools.StaticGameData()

        if "MS_ID_CHARACTER_BIOS_{}".format(self.mcocjson) in sgd.cdt_data:
            key = "MS_ID_CHARACTER_BIOS_{}".format(self.mcocjson)
        elif "ID_CHARACTER_BIOS_{}".format(self.mcocjson) in sgd.cdt_data:
            key = "ID_CHARACTER_BIOS_{}".format(self.mcocjson)
        elif "ID_CHARACTER_BIO_{}".format(self.mcocjson) in sgd.cdt_data:
            key = "ID_CHARACTER_BIO_{}".format(self.mcocjson)
        elif "ID_CHARACTER_BIOS_{}".format(self.mattkraftid) in sgd.cdt_data:
            key = "ID_CHARACTER_BIOS_{}".format(self.mattkraftid)
        else:
            await self.bot.say('Key not identified.')
            return

        if self.debug:
            dbg_str = "BIO:  " + key
            await self.bot.say('```{}```'.format(dbg_str))
        try:
            bio = sgd.cdt_data[key]
        except KeyError:
            raise KeyError('Cannot find Champion {} in data files'.format(self.full_name))
        return bio

    @property
    def star(self):
        return self._star

    @property
    def rank(self):
        return getattr(self, '_rank', self._default['rank'])

    @property
    def sig(self):
        return getattr(self, '_sig', self._default['sig'])

    def is_defined(self, attr):
        return hasattr(self, '_' + attr)

    @property
    def is_user_playable(self):
        return (self.released is not None
                and dateParse(self.released) <= datetime.now())

    @property
    def immutable_id(self):
        return (type(self), self.star)

    @property
    def duel_str(self):
        return '{0.star}{0.star_char} {0.rank}/{0.max_lvl} {0.full_name}'.format(self)

    @property
    def star_str(self):
        return '{0.stars_str} {0.rank}/{0.max_lvl}'.format(self)

    @property
    def attrs_str(self):
        return '{0.star}{0.star_char} {0.rank}/{0.max_lvl} sig{0.sig}'.format(self)

    @property
    def unique(self):
        return '{0.star}-{0.mattkraftid}-{0.rank}'.format(self)

    @property
    def coded_str(self):
        return '{0.star}*{0.short}r{0.rank}s{0.sig}'.format(self)

    @property
    def verbose_str(self):
        return '{0.star}{0.star_char} {0.full_name} r{0.rank}'.format(self)
        # return '{0.stars_str} {0.full_name} r{0.rank}'.format(self)

    @property
    def star_name_str(self):
        return '{0.star}{0.star_char} {0.full_name}'.format(self)
        #return '{0.star}★ {0.full_name}'.format(self)

    @property
    def rank_sig_str(self):
        return '{0.rank}/{0.max_lvl} sig{0.sig:<2}'.format(self)

    @property
    def verbose_prestige_str(self):
        return ('{0.class_icon} {0.star}{0.star_char} {0.full_name} '
                + 'r{0.rank} s{0.sig:<2} [ {0.prestige} ]').format(self)

    @property
    def stars_str(self):
        return self.star_char * self.star

    @property
    def terse_star_str(self):
        return '{0.star}{0.star_char}'.format(self)

    @property
    def star_char(self):
        if self.sig:
            return '★'
        else:
            return '☆'

    @property
    def chlgr_rating(self):
        if self.star == 1:
            return self.rank * 10
        if self.star == 6:
            return (2 * self.star - 2 + self.rank) * 10
        else:
            return (2 * self.star - 3 + self.rank) * 10

    @property
    def max_lvl(self):
        if self.star < 5:
            return self.rank * 10
        else:
            return 15 + self.rank * 10

    @property
    def all_tags(self):
        return self.tags.union(self.class_tags)

    def to_json(self):
        translate = {'sig': 'Awakened', 'hookid': 'Id', 'max_lvl': 'Level',
                    'prestige': 'Pi', 'rank': 'Rank', 'star': 'Stars',
                    'quest_role': 'Role', 'max_prestige': 'maxpi'}
        pack = {}
        for attr, hook_key in translate.items():
            pack[hook_key] = getattr(self, attr, '')
        return pack

    def get_special_attacks(self):
        sgd = cogs.mcocTools.StaticGameData()
        cdt_data = sgd.cdt_data
        prefix = 'ID_SPECIAL_ATTACK_'
        desc = 'DESCRIPTION_'
        zero = '_0'
        one = '_1'
        two = '_2'
        if prefix+self.mcocjson+one in cdt_data:
            s0 = cdt_data[prefix + self.mcocjson + zero]
            s1 = cdt_data[prefix + self.mcocjson + one]
            s2 = cdt_data[prefix + self.mcocjson + two]
            s0d = cdt_data[prefix + desc + self.mcocjson + zero]
            s1d = cdt_data[prefix + desc + self.mcocjson + one]
            s2d = cdt_data[prefix + desc + self.mcocjson + two]
            specials = (s0, s1, s2, s0d, s1d, s2d)
            return specials
        elif prefix+self.mcocsig+one in cdt_data:
            s0 = cdt_data[prefix + self.mcocsig + zero]
            s1 = cdt_data[prefix + self.mcocsig + one]
            s2 = cdt_data[prefix + self.mcocsig + two]
            s0d = cdt_data[prefix + desc + self.mcocsig + zero]
            s1d = cdt_data[prefix + desc + self.mcocsig + one]
            s2d = cdt_data[prefix + desc + self.mcocsig + two]
            specials = (s0, s1, s2, s0d, s1d, s2d)
            return specials


    @property
    @validate_attr('prestige')
    def prestige(self):
        try:
            if self.prestige_data[self.star][self.rank-1] is None:
                return 0
        except KeyError:
            return 0
        return self.prestige_data[self.star][self.rank-1][self.sig]

    @property
    def has_prestige(self):
        return hasattr(self, 'prestige_data')

    @property
    @validate_attr('prestige')
    def max_prestige(self):
        cur_rank = self.rank
        if self.star == 5:
            rank = 3 if cur_rank < 4 else 4
        else:
            rank = self.star + 1
        self.update_attrs({'rank': rank})
        maxp = self.prestige
        self.update_attrs({'rank': cur_rank})
        return maxp

    @validate_attr('prestige')
    def get_prestige_arr(self, rank, sig_arr, star=4):
        row = ['{}r{}'.format(self.short, rank)]
        for sig in sig_arr:
            try:
                row.append(self.prestige_data[star][rank-1][sig])
            except:
                logger.error(rank, sig, self.prestige_data)
                raise
        return row

    async def missing_sig_ad(self):
        em = discord.Embed(color=self.class_color,
                title='Signature Data is Missing')
        em.add_field(name=self.full_name,
                value='Contribute your data at http://discord.gg/BwhgZxk')
        await self.bot.say(embed=em)

    async def process_sig_description(self, data=None, quiet=False, isbotowner=False):
        sd = await self.retrieve_sig_data(data, isbotowner)
        try:
            ktxt = sd['kabam_text']
        except KeyError:
            raise MissingKabamText
        if self.debug:
            dbg_str = ['Title:  ' + ktxt['title']['k']]
            dbg_str.append('Simple:  ' + ktxt['simple']['k'])
            dbg_str.append('Description Keys:  ')
            dbg_str.append('  ' + ', '.join(ktxt['desc']['k']))
            dbg_str.append('Description Text:  ')
            dbg_str.extend(['  ' + self._sig_header(d)
                            for d in ktxt['desc']['v']])
            await self.bot.say(chat.box('\n'.join(dbg_str)))

        await self._sig_error_code_handling(sd, raise_error=quiet)
        if self.sig == 0:
            return self._get_sig_simple(ktxt)

        sig_calcs = {}
        try:
            stats = sd['spotlight_trunc'][self.unique]
        except (TypeError, KeyError):
            stats = {}
        self.stats_missing = False
        x_arr = self._sig_x_arr(sd)
        for effect, ckey, coeffs in zip(sd['effects'], sd['locations'], sd['sig_coeff']):
            if coeffs is None:
                await self.bot.say("**Data Processing Error**")
                if not quiet:
                    await self.missing_sig_ad()
                return self._get_sig_simple(ktxt)
            y_norm = sumproduct(x_arr, coeffs)
            sig_calcs[ckey] = self._sig_effect_decode(effect, y_norm, stats)

        if self.stats_missing:
            await self.bot.say(('Missing Attack/Health info for '
                    + '{0.full_name} {0.star_str}').format(self))

        brkt_re = re.compile(r'{([0-9])}')
        fdesc = []
        for i, txt in enumerate(ktxt['desc']['v']):
            fdesc.append(brkt_re.sub(r'{{d[{0}-\1]}}'.format(i),
                        self._sig_header(txt)))
        if self.debug:
            await self.bot.say(chat.box('\n'.join(fdesc)))
        title, desc, sig_calcs = ktxt['title']['v'], '\n'.join(fdesc), sig_calcs
        try:
            desc.format(d=sig_calcs)
        except KeyError as e:
            raise SignatureSchemaError("'{}' key error at {}".format(
                    self.full_name, str(e)))
        return title, desc, sig_calcs

    async def retrieve_sig_data(self, data, isbotowner):
        if data is None:
            try:
                sd = dataIO.load_json(local_files['signature'])[self.full_name]
            except KeyError:
                sd = self.init_sig_struct()
            except FileNotFoundError:
                if isbotowner:
                    await self.bot.say("**DEPRECIATION WARNING**  "
                            + "Couldn't load json file.  Loading csv files.")
                sd = self.get_sig_data_from_csv()
            cfile = 'sig_coeff_4star' if self.star < 5 else 'sig_coeff_5star'
            coeff = dataIO.load_json(local_files[cfile])
            try:
                sd.update(coeff[self.full_name])
            except KeyError:
                sd.update(dict(effects=[], locations=[], sig_coeff=[]))
        else:
            sd = data[self.full_name] if self.full_name in data else data
        return sd

    async def _sig_error_code_handling(self, sd, raise_error=False):
        if 'error_codes' not in sd or sd['error_codes']['undefined_key']:
            if raise_error:
                raise MissingSignatureData
            await self.warn_bold_say('Champion Signature data is not defined')
            self.update_attrs(dict(sig=0))
        elif sd['error_codes']['no_curve']:
            if raise_error:
                raise InsufficientData
            await self.warn_bold_say('{} '.format(self.star_name_str)
                    + 'does not have enough data points to create a curve')
            self.update_attrs(dict(sig=0))
        elif sd['error_codes']['low_count']:
            if raise_error:
                raise LowDataWarning
            await self.warn_bold_say('{} '.format(self.star_name_str)
                    + 'has low data count.  Unknown estimate quality')
        elif sd['error_codes']['poor_fit']:
            if raise_error:
                raise PoorDataFit
            await self.warn_bold_say('{} '.format(self.star_name_str)
                    + 'has poor curve fit.  Data is known to contain errors.')

    def _sig_x_arr(self, sig_dict):
        fit_type = sig_dict['fit_type'][0]
        if fit_type.startswith('lin'):
            x_var = float(self.sig)
        elif fit_type.startswith('log'):
            x_var = log(self.sig)
        else:
            raise AttributeError("Unknown fit_type '{}' for champion {}".format(
                    fit_type, self.full_name ))
        if fit_type.endswith('quad'):
            return x_var**2, x_var, 1
        elif fit_type.endswith('lin'):
            return x_var, 1
        else:
            raise AttributeError("Unknown fit_type '{}' for champion {}".format(
                    fit_type, self.full_name ))

    def _sig_effect_decode(self, effect, y_norm, stats):
        if effect == 'raw':
            if y_norm.is_integer():
                calc = '{:.0f}'.format(y_norm)
            else:
                calc = '{:.2f}'.format(y_norm)
        elif effect == 'flat':
            calc = self.sig_per_str.format(
                    to_flat(y_norm, self.chlgr_rating), y_norm/100)
        elif effect == 'attack':
            if 'attack' not in stats:
                self.stats_missing = True
                calc = self.sig_raw_per_str.format(y_norm/100)
            else:
                calc = self.sig_per_str.format(
                        stats['attack'] * y_norm / 100, y_norm/100)
        elif effect == 'health':
            if 'health' not in stats:
                self.stats_missing = True
                calc = self.sig_raw_per_str.format(y_norm/100)
            else:
                calc = self.sig_per_str.format(
                        stats['health'] * y_norm / 100, y_norm/100)
        else:
            raise AttributeError("Unknown effect '{}' for {}".format(
                    effect, self.full_name))
        return calc

    def _get_sig_simple(self, ktxt):
        return ktxt['title']['v'], ktxt['simple']['v'], None

    def get_sig_data_from_csv(self):
        struct = self.init_sig_struct()
        coeff = self.get_sig_coeff()
        ekey = self.get_effect_keys()
        spotlight = self.get_spotlight()
        if spotlight and spotlight['attack'] and spotlight['health']:
            stats = {k:int(spotlight[k].replace(',',''))
                        for k in ('attack', 'health')}
        else:
            stats = {}
        struct['spotlight_trunc'] = {self.unique: stats}
        if coeff is None or ekey is None:
            return struct
        for i in map(str, range(6)):
            if not ekey['Location_' + i]:
                break
            struct['effects'].append(ekey['Effect_' + i])
            struct['locations'].append(ekey['Location_' + i])
            try:
                struct['sig_coeff'].append((float(coeff['ability_norm' + i]),
                      float(coeff['offset' + i])))
            except:
                struct['sig_coeff'] = None
        return struct

    def init_sig_struct(self):
        return dict(effects=[], locations=[], sig_coeff=[],
                #spotlight_trunc={self.unique: stats},
                kabam_text=self.get_kabam_sig_text())

    def get_kabam_sig_text(self, sigs=None, champ_exceptions=None):
        '''required for signatures to work correctly
        preamble
        title = titlekey,
        simplekey = preample + simple
        descriptionkey = preamble + desc,
        '''

        sgd = cogs.mcocTools.StaticGameData()
        if sgd.cdt_data is None:
            print("Sig Error: {} isn't pulling game data".format(self.mcocsig))
            raise TitleError(self.full_name)
        mcocsig = self.mcocsig
        if not self._TITLE or not self._SIMPLE or not self._DESC_LIST:
            print("Title Error <{}:{}> title: {}, simple: {}, desc_list: {}".format(
                    self.full_name, mcocsig,
                    self._TITLE, self._SIMPLE, self._DESC_LIST
            ))
            raise TitleError(self.full_name)
        title = self._TITLE
        #print(title)
        simple = self._SIMPLE
        #print(simple)
        #print(mcocsig, self._TITLE, self._DESC_LIST)
        desc = [key.strip() for key in self._DESC_LIST.split(',') if key.strip()]

        # allow manual override of Kabam Keys
        champ_exceptions = champ_exceptions if champ_exceptions else {}
        keymap = sgd.cdt_data.new_child(champ_exceptions)
        return dict(title={'k': title, 'v': keymap[title]},
                    simple={'k': simple, 'v': keymap[simple]},
                    desc={'k': desc, 'v': [keymap[k] for k in desc]})


    def get_sig_coeff(self):
        return get_csv_row(local_files['sig_coeff'], 'CHAMP', self.full_name)

    def get_effect_keys(self):
        return get_csv_row(local_files['effect_keys'], 'CHAMP', self.full_name)

    def get_spotlight(self, default=None):
        return get_csv_row(data_files['spotlight']['local'], 'unique',
                self.unique, default=default)

    def get_aliases(self):
        return '```{}```'.format(', '.join(self.alias_set))

    @staticmethod
    def _sig_header(str_data):
        hex_re = re.compile(r'\[[0-9a-f]{6,8}\](.+?)\[-\]', re.I)
        return '• ' + hex_re.sub(r'**\1**', str_data)

def bound_lvl(siglvl, max_lvl=99):
    if isinstance(siglvl, list):
        ret = []
        for j in siglvl:
            if j > max_lvl:
                j = max_lvl
            elif j < 0:
                j = 0
            ret.append(j)
    else:
        ret = siglvl
        if siglvl > max_lvl:
            ret = max_lvl
        elif siglvl < 0:
            ret = 0
    return ret

def _get_role(server, role_key: str):
    """Returns discord.Role"""
    for role in server.roles:
        if role.id == role_key:
            return role
    return None

def tabulate(table_data, width, rotate=True, header_sep=True, align_out=True):
    rows = []
    cells_in_row = None
    for i in iter_rows(table_data, rotate):
        if cells_in_row is None:
            cells_in_row = len(i)
        elif cells_in_row != len(i):
            raise IndexError("Array is not uniform")
        if align_out:
            fstr = '{:<{width}}'
            if len(i) > 1:
                fstr += '|' + '|'.join(['{:>{width}}']*(len(i)-1))
            rows.append(fstr.format(*i, width=width))
        else:
            rows.append('|'.join(['{:^{width}}']*len(i)).format(*i, width=width))
    if header_sep:
        rows.insert(1, '|'.join(['-' * width] * cells_in_row))
    return chat.box('\n'.join(rows))

def sumproduct(arr1, arr2):
    return sum([x * y for x, y in zip(arr1, arr2)])
    # return sum([float(x) * float(y) for x, y in zip(arr1, arr2)])

def iter_rows(array, rotate):
    if not rotate:
        for i in array:
            yield i
    else:
        for j in range(len(array[0])):
            row = []
            for i in range(len(array)):
                row.append(array[i][j])
            yield row

def load_kabam_json(file, aux=None):
    raw_data = dataIO.load_json(file)
    data = ChainMap()
    aux = aux if aux is not None else []
    for dlist in aux, raw_data['strings']:
        data.maps.append({d['k']:d['v'] for d in dlist})
    return data

def _truncate_text(self, text, max_length):
    if len(text) > max_length:
        if text.strip('$').isdigit():
            text = int(text.strip('$'))
            return "${:.2E}".format(text)
        return text[:max_length-3] + "..."
    return text

def get_csv_row(filecsv, column, match_val, default=None):
    logger.debug(match_val)
    csvfile = load_csv(filecsv)
    for row in csvfile:
        if row[column] == match_val:
            if default is not None:
                for k, v in row.items():
                    if v == '':
                        row[k] = default
            return row

def get_csv_rows(filecsv, column, match_val, default=None):
    logger.debug(match_val)
    csvfile = load_csv(filecsv)
    package =[]
    for row in csvfile:
        if row[column] == match_val:
            if default is not None:
                for k, v in row.items():
                    if v == '':
                        row[k] = default
            package.append(row)
    return package

def load_csv(filename):
    return csv.DictReader(open(filename))

def padd_it(word,max : int,opt='back'):
    loop = max-len(str(word))
    if loop > 0:
        padd = ''
        for i in loop:
            padd+=' '
        if opt =='back':
            return word+padd
        else:
            return padd+word
    else:
        logger.warn('Padding would be negative.')

async def raw_modok_says(bot, channel, word=None):
    if not word or word not in MODOKSAYS:
        word = random.choice(MODOKSAYS)
    modokimage='{}images/modok/{}.png'.format(remote_data_basepath, word)
    em = discord.Embed(color=CDT_COLORS['Science'],
            title='M.O.D.O.K. says', description='')
    em.set_image(url=modokimage)
    await bot.send_message(channel, embed=em)

def override_error_handler(bot):
    if not hasattr(bot, '_command_error_orig'):
        bot._command_error_orig = bot.on_command_error
    @bot.event
    async def on_command_error(error, ctx):
        if isinstance(error, MODOKError):
            bot.logger.info('<{}> {}'.format(type(error).__name__, error))
            await bot.send_message(ctx.message.channel, "\u26a0 " + str(error))
            await raw_modok_says(bot, ctx.message.channel)
        elif isinstance(error, QuietUserError):
            #await bot.send_message(ctx.message.channel, error)
            bot.logger.info('<{}> {}'.format(type(error).__name__, error))
        else:
            await bot._command_error_orig(error, ctx)

# avoiding cyclic importing
from . import hook as hook
import cogs.mcocTools
from .mcocTools import (KABAM_ICON, COLLECTOR_ICON, PagesMenu,
    GSHandler, gapi_service_creds, GSExport, CDT_COLORS, StaticGameData)

def setup(bot):
    override_error_handler(bot)
    bot.add_cog(MCOC(bot))
