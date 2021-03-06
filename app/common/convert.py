# Artshow Keeper: A support tool for keeping an Artshow running.
# Copyright (C) 2014  Ivo Hanak
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import json
from decimal import Decimal
from decimal import InvalidOperation
from datetime import datetime

def toNonEmptyStr(value, default=None):
    """Convert a value to a string if not None or empty string.
    Returns:
        string or supplied default
    """
    if value is None:
        return default
    elif isinstance(value, str) and len(value) == 0:
        return default
    else:
        return str(value)

def toQuotedStr(list):
    """Convert a list to a string of quoted values separated by a comma.
    """
    if list is None:
        return None
    else:
        return ','.join(['"' + str(member) + '"' for member in list])

def toQuoteSafeStr(value):
    """Convert a string to quote safe string such that is can be used with eval.
    Example:
        ab"cd -> ab\"cd
    """
    if value is None:
        return None
    else:
        return str(value).replace('"', '\\"')

def toDecimal(value):
    try:
        return Decimal(value if value is not None else 'X')
    except InvalidOperation:
        return None

def toInt(value):
    if value is None:
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def toDateTime(value):
    if value is None:
        return None
    try:
        return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S.%f')
    except ValueError:
        return None


def checkRange(value, lower, upper):
    """Check whether a value is within a range [lower, upper].
    Args:
        value -- Value.
        lower -- Lower boundary of the range. None if -infinity.
        upper -- Upper boundary of the range. None if +infinity.
    Returns:
        Value or None on error.
    """
    if value is None:
        return None
    elif lower is not None and value < lower:
        return None
    elif upper is not None and value > upper:
        return None
    else:
        return value

class JSONDecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        else:
            return json.JSONEncoder.default(self, obj)
