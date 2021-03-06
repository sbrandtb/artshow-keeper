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
import logging
import random
import json
import os
import sys
from os import path
from PIL import Image

from model.attendee import Attendee
from . item import ItemState, ItemField, ImportedItemField
from . currency_field import CurrencyField
from . session import Field as SessionField

from . table import Table
from common.convert import *
from common.result import Result

class Dataset:
    GLOBAL_SESSION_ID = 0
    RESERVED_ITEM_EXPRESSION = 'Owner is None and Author is None and Title is None'

    def __init__(
            self, logger, dataPath,
            sessionFilename='sessiondictionary.xml',
            itemsFilename='artshowitems.xml',
            currencyFilename='currency.xml',
            attendeesFilename='attendees.xml',
    ):
        self.__logger = logger
        self.__dataPath = dataPath
        self.__imageDataPath = path.join(self.__dataPath, 'image')
        self.__sessions = Table(
                self.__logger,
                path.join(self.__dataPath, sessionFilename),
                'SessionDictionary',
                'KeyValuePair',
                ['SessionID', 'Key', 'Value'])
        self.__items = Table(
                self.__logger, path.join(self.__dataPath, itemsFilename),
                'ArtShowItems',
                'Item',
                ItemField.ALL_PERSISTENT)
        self.__currency = Table(
                self.__logger,
                path.join(self.__dataPath, currencyFilename),
                'CurrencyList',
                'Currency',
                CurrencyField.ALL_PERSISTENT)
        self.__attendees = Table(
                self.__logger,
                path.join(self.__dataPath, attendeesFilename),
                'Attendees',
                'Attendee',
                Attendee.ALL_PERSISTENT)

        self.__jsonDecoder = json.JSONDecoder()
        self.__jsonEncoder = json.JSONEncoder()

    def items(self):
        return self.__items
        
    def restore(self):
        self.__sessions.load()
        self.__items.load()
        self.__currency.load()
        self.__attendees.load()
        
    def persist(self):
        self.__sessions.save()
        self.__items.save()
        self.__currency.save()
        self.__attendees.save()

    def getClientSessionIDs(self):
        rawSessions = self.__sessions.select(
                ['SessionID'],
                'SessionID != "{0}"'.format(self.GLOBAL_SESSION_ID))
        sessions = {}
        for rawSession in rawSessions:
            id = toInt(rawSession['SessionID'])
            if id != self.GLOBAL_SESSION_ID:
                sessions[id] = True
        return [value for value in sessions.keys()]

    def getSessionPairs(self, sessionID):
        rawPairs = self.__sessions.select(
                ['Key', 'Value'],
                'SessionID == "{0}"'.format(sessionID))
        pairs = { rawPair['Key']: rawPair['Value'] for rawPair in rawPairs }
        return pairs
        
    def getSessionValue(self, sessionID, key, defaultValue = None):
        """Retrieve a value of a given key in a given session.
        Args:
            sessionID -- Session ID.
            key -- Key of the value.
            defaultValue -- Returned value if the combination (sessionID, key) is not found.
        Returns:
            Value or defaultValue if not found.
        """
        rawValue = self.__sessions.select(
                ['Value'],
                'SessionID == "{0}" and Key == "{1}"'.format(sessionID, key))
        if len(rawValue) > 0:
            return str(rawValue[0]['Value'])
        else:
            return defaultValue

    def updateSessionPairs(self, sessionID, **pairs):
        """Update session pairs.
        Returns:
            True if the update was successful.
        """
        updated = False
        for key, value in pairs.items():
            rawPair = { 'SessionID': str(sessionID), 'Key': str(key), 'Value': value }
            if value != None:
                updated = self.__sessions.update(rawPair, 'SessionID == "{0}" and Key == "{1}"'.format(sessionID, key)) > 0 \
                        or self.__sessions.insert(rawPair, None) > 0
            else:
                updated = self.__sessions.delete('SessionID == "{0}" and Key == "{1}"'.format(sessionID, key)) > 0
        return updated

    def dropValidSession(self, sessionID):
        """Remove a sessions."""
        if toInt(sessionID) != 0:
            self.__sessions.delete('SessionID == "{0}"'.format(sessionID))


    def getGlobalValue(self, key, defaultValue = None):
        return self.getSessionValue(self.GLOBAL_SESSION_ID, key, defaultValue)
    
    def updateGlobalPairs(self, **pairs):
        return self.updateSessionPairs(self.GLOBAL_SESSION_ID, **pairs)    

    def getGlobalDict(self, key, defaultValue = {}):
        try:
            textJSON = self.getSessionValue(self.GLOBAL_SESSION_ID, key, None)
            if textJSON is None:
                return defaultValue
            else:
                return self.__jsonDecoder.decode(str(textJSON))
        except json.JSONDecodeError:
            return defaultValue

    def updateGlobalDict(self, key, dict):
        if dict is not None:
            return self.updateSessionPairs(self.GLOBAL_SESSION_ID, **{
                    key: self.__jsonEncoder.encode(dict)})
        else:
            return self.updateGlobalPairs(self.GLOBAL_SESSION_ID, **{
                    key: None });


    def __isReservedItem(self, item):
        """Return true if the item is reserved item."""
        return item.get(ItemField.OWNER, None) is None and \
            item.get(ItemField.AUTHOR, None) is None and \
            item.get(ItemField.TITLE, None) is None

    def getNextItemCode(self, suggestedCode=None, requestSuggestedCode=False):
        """Get next item code.
        Args:
            suggestedCode -- Code that should be used if possible.
            requestSuggestedCode -- True to fail the call prior updating dataset if Suggested Code cannot be used.
        Returns:
            Code (string) or None on failure.
        """
        # Retrive reserved code
        reservedItemExpression = self.RESERVED_ITEM_EXPRESSION
        reservedItems = self.__items.select([ItemField.CODE], reservedItemExpression)
        reservedCode = None
        if len(reservedItems) == 1:
            reservedCode = toInt(reservedItems[0][ItemField.CODE])
        elif len(reservedItems) > 1:
            self.__logger.warning('getNextItemCode: Found {0} reserved items. Item code will be re-calculated.'.format(len(reservedItems)))

        # If no reserved code is found, estimate it
        if reservedCode == None:
            reservedCode = 0
            items = self.__items.select([ItemField.CODE], None)
            for item in items:
                code = toInt(item[ItemField.CODE])
                if code is not None and code > reservedCode:
                    reservedCode = code
            reservedCode = reservedCode + 1
            self.__logger.info('getNextItemCode: Reserved code has been estimated to {0}.'.format(reservedCode))

        # Reserve the next item code
        if suggestedCode is not None:
            if toInt(suggestedCode) >= reservedCode:
                reservedCode = toInt(suggestedCode)
            elif requestSuggestedCode:
                return None
        nextReservedCode = reservedCode + 1

        # Store result
        self.__items.delete(reservedItemExpression)
        while not self.__items.insert({ItemField.CODE: str(nextReservedCode)}, ItemField.CODE):
            nextReservedCode = nextReservedCode + random.randint(1, 10)

        return str(reservedCode)

    def addItem(self, code, owner, title, author, medium, state, initialAmount, charity, note, importNumber):
        if len(str(code)) == 0:
            self.__logger.error('addItem: Code is invalid')
            return False
        elif toInt(owner) is None:
            self.__logger.error('addItem: Onwer "{0}" is invalid'.format(owner))
            return False
        elif importNumber is not None and toInt(importNumber) is None:
            self.__logger.error('addItem: Import number "{0}" is invalid'.format(importNumber))
            return False
        else:
            return self.__items.insert(
                    {
                        ItemField.CODE: str(code),
                        ItemField.OWNER: str(owner),
                        ItemField.TITLE: str(title),
                        ItemField.AUTHOR: str(author),
                        ItemField.MEDIUM: toNonEmptyStr(medium),
                        ItemField.STATE: str(state),
                        ItemField.INITIAL_AMOUNT: toNonEmptyStr(toDecimal(initialAmount)),
                        ItemField.CHARITY: toNonEmptyStr(toInt(charity)),
                        ItemField.NOTE: toNonEmptyStr(note),
                        ItemField.IMPORT_NUMBER: str(importNumber) },
                    ItemField.CODE)                    

    def normalizeItemImport(self, itemImport):
        """Normalizes item import.
        Returns:
            (result, item).
        """
        item = {
                ImportedItemField.NUMBER: None,
                ImportedItemField.OWNER: None,
                ImportedItemField.AUTHOR: None,
                ImportedItemField.TITLE: None,
                ImportedItemField.MEDIUM: None,
                ImportedItemField.NOTE: None,
                ImportedItemField.INITIAL_AMOUNT: None,
                ImportedItemField.CHARITY: None }

        component = itemImport.get(ImportedItemField.NUMBER, None)
        number = toInt(component)
        if number is None and component is not None and len(component) > 0:
            self.__logger.error('purifyRawItemImport:  Number "{0}" is not an integer.'.format(component))
            return Result.INVALID_ITEM_NUMBER, item
        item[ImportedItemField.NUMBER] = number

        component = itemImport.get(ImportedItemField.OWNER, None)
        owner = toInt(component)
        if owner is None and component is not None and len(component) > 0:
            self.__logger.error('purifyRawItemImport:  Owner "{0}" is not an integer.'.format(component))
            return Result.INVALID_ITEM_OWNER, item
        item[ImportedItemField.OWNER] = owner

        item[ImportedItemField.AUTHOR] = toNonEmptyStr(
                itemImport.get(ImportedItemField.AUTHOR, None))            

        item[ImportedItemField.TITLE] = toNonEmptyStr(
                itemImport.get(ImportedItemField.TITLE, None))            

        item[ImportedItemField.MEDIUM] = toNonEmptyStr(
                itemImport.get(ImportedItemField.MEDIUM, None))            

        item[ImportedItemField.NOTE] = toNonEmptyStr(
                itemImport.get(ImportedItemField.NOTE, None))            

        component = itemImport.get(ImportedItemField.INITIAL_AMOUNT, None)
        amount = toDecimal(component)
        if amount is None and component is not None and len(component) > 0:
            self.__logger.error('purifyRawItemImport:  Amount "{0}" is not a decimal number.'.format(component))
            return Result.INVALID_AMOUNT, item
        item[ImportedItemField.INITIAL_AMOUNT] = str(amount) if amount is not None else None

        component = itemImport.get(ImportedItemField.CHARITY, None)
        charity = toInt(component)
        if charity is None and component is not None and len(component) > 0:
            self.__logger.error('purifyRawItemImport:  Charity "{0}" is not an integer.'.format(component))
            return Result.INVALID_CHARITY, item
        item[ImportedItemField.CHARITY] = charity

        return Result.SUCCESS, item

    def __normalizeItem(self, item):
        """Normalize item data types."""
        item[ItemField.OWNER] = toInt(item[ItemField.OWNER])
        item[ItemField.BUYER] = toInt(item[ItemField.BUYER])
        item[ItemField.CHARITY] = toInt(item[ItemField.CHARITY])
        item[ItemField.INITIAL_AMOUNT] = toDecimal(item[ItemField.INITIAL_AMOUNT])
        item[ItemField.AMOUNT] = toDecimal(item[ItemField.AMOUNT])
        item[ItemField.AMOUNT_IN_AUCTION] = toDecimal(item[ItemField.AMOUNT_IN_AUCTION])
        item[ItemField.IMPORT_NUMBER] = toInt(item[ItemField.IMPORT_NUMBER])
        return item

    def getAttendees(self):
        raw_attendees = self.__attendees.select(Attendee.ALL_PERSISTENT)
        return [Attendee.load(raw) for raw in raw_attendees]

    def getAttendee(self, regId):
        try:
            return Attendee.load(
                self.__attendees.select(
                    Attendee.ALL_PERSISTENT,
                    '{col} == "{id:d}"'.format(col=Attendee.REG_ID, id=int(regId))
                )[0])
        except IndexError:
            return Attendee.load({
                Attendee.REG_ID: regId,
                Attendee.NICKNAME: '<unknown>',
            })


    def getItems(self, expression):
        """Get items based on expression. Exclude reserved item.
        Returns:
            Items.
        """
        items = self.__items.select(ItemField.ALL_PERSISTENT, expression)
        items[:] = [self.__normalizeItem(item) for item in items if not self.__isReservedItem(item)]
        return items

    def getItem(self, itemCode):
        if itemCode is None:
            return None
        else:
            items = self.getItems('Code == "{0}"'.format(itemCode))
            if len(items) == 0:
                self.__logger.error('updateItem: Item {0} not found.'.format(itemCode))
                return None
            elif len(items) != 1:
                self.__logger.error('updateItem: Item "{0}" ({1}) has {2} duplicates.'.format(
                    itemCode, str(items), len(items)))
                return None
            else:
                return items[0]

    def __unifyFields(self, fields):
        """Unify item fiels to pairs (string, string) or (string, None)."""
        return {key: toNonEmptyStr(value) for key, value in fields.items()}

    def updateItem(self, itemCode, **item):
        """Update an item of a given item code.
        Args:
            itemCode -- Item code.
            item -- Fields to update (keywords arguments).
        Return:
            True if update succeeded.
        """
        if itemCode is None:
            self.__logger.error('updateItem: Item code is invalid.')
            return False
        elif ItemField.CODE in item and item[ItemField.CODE] != itemCode:
            self.__logger.error('updateItem: Item code "{0}" does not match item code "{1}" in the item structure.'.format(
                    itemCode, item[ItemField.CODE]))
            return False
        elif self.__items.update(self.__unifyFields(item), 'Code == "{0}"'.format(itemCode)) != 1:
            self.__logger.error('updateItem: Item "{0}" has not been updated.'.format(itemCode))
            return False
        else:
            self.__logger.info('updateItem: Item "{0}" has been updated with: {1}'.format(
                    itemCode, json.dumps(item, cls=JSONDecimalEncoder)))
            return True

    def updateMultipleItems(self, expression, **fields):
        """Update multiple items that satisfies the expression.
        Args:
            expression -- Expresision to use.
            fields -- Fields to update (keywords arguments).
        Return:
            Number (int) of items that were updated.
        """
        if expression is None:
            self.__logger.error('updateMultipleItems: Expression is invalid.')
            return 0
        elif fields is None or len(fields) == 0:
            self.__logger.info(
                    'updateMultipleItems: Not updated using expression "{0}" because update data are empty.'.format(
                            expression))
            return 0
        else:
            numUpdated = self.__items.update(self.__unifyFields(fields), expression)
            self.__logger.info(
                    'updateMultipleItems: Expression "{0}" updated {1} item(s) with: {2}'.format(
                            expression, numUpdated, json.dumps(fields, cls=JSONDecimalEncoder)))
            return numUpdated

    def countItems(self, expression):
        """Count a number of items that matches the expression.
        """
        return self.__items.count(expression)

    def __normalizeCurrencyInfo(self, currencyInfo):
        """Normalize currency info types."""
        currencyInfo[CurrencyField.AMOUNT_IN_PRIMARY] = toDecimal(currencyInfo[CurrencyField.AMOUNT_IN_PRIMARY])
        currencyInfo[CurrencyField.DECIMAL_PLACES] = toInt(currencyInfo[CurrencyField.DECIMAL_PLACES])
        currencyInfo[CurrencyField.FORMAT_PREFIX] = currencyInfo[CurrencyField.FORMAT_PREFIX] or ''
        currencyInfo[CurrencyField.FORMAT_SUFFIX] = currencyInfo[CurrencyField.FORMAT_SUFFIX] or ''
        return currencyInfo

    def getCurrencyInfo(self, currencyCodes):        
        """Retrieve currency info for a list of currencies.
        Args:
            currecnyCodes(list): List of currencies (e.g. ['czk', 'eur']).
        Returns:
            List of dict(CurrencyField) ordered according to the input list.
                A dictionary containing just the code is used in a place of a currency which is not found.
        """
        currencyInfoList = self.__currency.select(
                CurrencyField.ALL_PERSISTENT,
                'Code in [{0}]'.format(toQuotedStr(currencyCodes)))
        currencyInfoList[:] = [self.__normalizeCurrencyInfo(info) for info in currencyInfoList]
        
        # order by the input list
        # expect just a minimal number of currencies (3 - 5).
        orderedCurrencyInfoList = []
        for code in currencyCodes:
            try:
                orderedCurrencyInfoList.append(next(info for info in currencyInfoList if info[CurrencyField.CODE] == code))
            except StopIteration:
                orderedCurrencyInfoList.append({
                    CurrencyField.CODE: code})

        return orderedCurrencyInfoList

    def updateCurrencyInfo(self, currencyInfoList):
        """ Update currency info.
        """
        if currencyInfoList is None or len(currencyInfoList) == 0:
            self.__logger.info('updateCurrencyInfo: List in empty.')
            return Result.SUCCESS
        else:
            # check input
            for currencyInfo in currencyInfoList:
                code = currencyInfo.get(CurrencyField.CODE, None)
                if code is None:
                    self.__logger.error('updateCurrencyInfo: Input "{0}" does not include currency code.'.format(
                            json.dumps(currencyInfo, cls=JSONDecimalEncoder)))
                    return Result.INPUT_ERROR

                amountInPrimary = toDecimal(currencyInfo.get(CurrencyField.AMOUNT_IN_PRIMARY, None))
                if amountInPrimary is None:
                    self.__logger.error('updateCurrencyInfo: Currency code "{0}" does not contain a valid amount-in-primary ({1}).'.format(
                            currencyInfo[CurrencyField.CODE], currencyInfo.get(CurrencyField.AMOUNT_IN_PRIMARY, '<missing>')))
                    return Result.INPUT_ERROR
                currencyInfo[CurrencyField.AMOUNT_IN_PRIMARY] = amountInPrimary

            # apply input
            updated = 0
            for currencyInfo in currencyInfoList:
                if self.__currency.update({
                            CurrencyField.AMOUNT_IN_PRIMARY: currencyInfo[CurrencyField.AMOUNT_IN_PRIMARY]}, 'Code == "{0}"'.format(toQuoteSafeStr(currencyInfo[CurrencyField.CODE]))) == 1:
                    updated = updated + 1
                else:
                    self.__logger.error('updateCurrencyInfo: Currency "{0}" failed to update. Skipping.'.format(
                            currencyInfo[CurrencyField.CODE]))

            # report result
            if updated == len(currencyInfoList):
                return Result.SUCCESS
            else:
                return Result.PARTIAL_SUCCESS

    def __getItemJpgImageFilename(self, itemCode):
        return self.__imageDataPath, 'item{0}.jpg'.format(itemCode)

    def updateItemImage(self, itemCode, imageFile):
        result = Result.ERROR

        imagePath, imageFilename = self.__getItemJpgImageFilename(itemCode)
        imageFilePath = path.join(imagePath, imageFilename)
        imageTempFilePath = imageFilePath + '.tmp'

        if os.path.isfile(imageTempFilePath):
            os.remove(imageTempFilePath)
        if imageFile is not None:
            imageFile.save(imageTempFilePath)

            try:
                img = Image.open(imageTempFilePath)
                exifData = img._getexif()

                img.thumbnail((800, 800))

                orientation = exifData.get(0x0112, 0) if exifData is not None else 0 # Orientation
                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)

                img.save(imageFilePath, "JPEG")
                result = Result.SUCCESS
            except:
                self.__logger.error('updateItemImage: Image of item {0} cannot be processed: {1}.'.format(
                        itemCode, sys.exc_info()))
                result = Result.UNSUPPORTED_IMAGE_FORMAT

        if os.path.isfile(imageTempFilePath):
            os.remove(imageTempFilePath)
        if result != Result.SUCCESS and os.path.isfile(imageFilePath):
            os.remove(imageFilePath)
        return result

    def getItemJpgImage(self, itemCode):
        imagePath, imageFilename = self.__getItemJpgImageFilename(itemCode)
        imageFullPath = path.join(imagePath, imageFilename)
        if path.isfile(imageFullPath):
            return imagePath, imageFilename, str(int(path.getmtime(imageFullPath)))
        else:
            return None, None, None
