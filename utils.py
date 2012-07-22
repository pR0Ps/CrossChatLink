
import threading
import logging

class UserData():
    """Data structure for holding user data"""

    #to access array indecies and values by name
    PM = 0
    MC = 1
    CTRL = 2
    YES = 'Y'
    NO = 'N'
    UNSET = 'U'

    def __init__(self, initial = None):
        """Expects initial to be a list of lists like [[name, pm, mc, ctrl]]"""

        self.__users = dict()
        if initial != None:
            for x in initial:
                #TODO: error checking
                self.__users[x[0]] = [x[1], x[2], x[3]]

    def addUser(self, nick, pm, mc, ctrl):
        """adds/modifies a user"""

        #TODO: Error checking
        self.__users[nick] = [pm, mc, ctrl]

    def delUser(self, nick):
        """delete a user (when they logout)"""

        if nick in self.__users:
            del self.__users[nick]
        else:
            logging.warning("Deleting a user that doesn't exist")
            

    def getAttr(self, nick, idx):
        """get attributes of a user"""
        
        if not idx in [self.PM, self.MC, self.CTRL]:
            raise "Invalid user attribute"
        if nick in self.__users:
            return self.__users[nick][idx]

        logging.warning("Getting attributes for a user that doesn't exist")
        return UNSET
    
    def setAttr(self, nick, idx, val):
        if not idx in [self.PM, self.MC, self.CTRL]:
            raise "Invalid user attribute"
        elif not val in [self.YES, self.NO, self.UNSET]:
            raise "Invalid user attribute value"

#############################################################################
##class RepeatTimer(threading.Thread):
##    """Repeatedly calls a function every interval"""
##
##    def __init__(self, interval, callback, *args, **kwargs):
##        threading.Thread.__init__(self)
##        self.interval = interval
##        self.callable = callback
##        self.args = args
##        self.kwargs = kwargs
##        self.event = threading.Event()
##        self.event.set()
##
##    def run(self):
##        while self.event.is_set():
##            t = threading.Timer(self.interval, self.callback, self.args, self.kwargs)
##            t.start()
##            t.join()
##
##    def cancel(self):
##        self.event.clear()


def escapeReplace(msg, escChar, escData):
    """
    Replaces escape sequences with the corrisponding characters
    escChar: Char to signify an escape (usually a backslash)
    escData: A dictionary holding mappings of escapes to characters
    """
    if len(escChar) != 1:
        raise ValueError ("Escape indicator has to be a character")
    
    #stores the string as its built (faster than a non-mutable string)
    tempArr = []
    i = 0
    while  i < len(msg):
        #take data to the next escChar
        idx = msg.find(escChar, i)
        if (idx == -1):
            tempArr.append(msg[i:])
            break;
        else:
            tempArr.append(msg[i:idx])
            i = idx

        #msg[i] is the escape char
        #if theres a match for the escape, take the match
        for esc in escData:
            if msg[i + 1: i + len(esc) + 1] == esc:
                tempArr.append(escData[esc])
                i += len(esc) + 1
                break
        else: #yes, this is a for-else construct, no, it isn't indented improperly
            #didn't find anything, just take the escChar as literal
            tempArr.append(msg[i])
            i += 1
    return "".join(tempArr)























    
