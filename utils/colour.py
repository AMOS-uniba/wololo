import colorama
from colorama import Fore, Style


colorama.init()

def colour(what, how):
    return "{}{}{}".format(how, what, Style.RESET_ALL)


def ok(what):
    return colour(what, Fore.GREEN)


def num(what):
    return colour(what, Fore.LIGHTMAGENTA_EX)


def act(what):
    return colour(what, Fore.LIGHTGREEN_EX)


def warn(what):
    return colour(what, Fore.LIGHTYELLOW_EX)


def err(what):
    return colour(what, Fore.LIGHTRED_EX)


def critical(what):
    return colour(what, Fore.RED)


def path(what):
    return colour(what, Fore.LIGHTCYAN_EX)


def name(what):
    return colour(what, Fore.YELLOW)


def over(what):
    return colour(what, Fore.LIGHTGREEN_EX)


def codec(what):
    return colour(what, Fore.LIGHTMAGENTA_EX)


def param(what):
    return colour(what, Fore.LIGHTYELLOW_EX)


def debug(what):
    return colour(what, Fore.LIGHTBLACK_EX)


def none(what):
    return colour(what, Fore.WHITE)