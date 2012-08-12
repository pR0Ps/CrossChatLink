
import threading
import socket
import queue
import logging

import utils

class Link(threading.Thread):
    """Holds properties and methods common to DC and IRC links"""

    #For accessing the correct queues
    MAIN = 0
    PM = 1

    #Connection states
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    

    def __init__(self, program, server, nick, passwd, prefix, links, auto_connect, auto_reconnect, mc_rate, pm_rate, op_control, users):
        super(Link, self).__init__()

        if type(self) == Link:
            raise Exception("Link must be subclassed")

        #linkback to main
        self._program = program
        
        #settings
        self.server = server
        self.nick = nick
        self.passwd = passwd
        self.prefix = prefix
        self._links = links
        self.auto_connect = auto_connect
        self.auto_reconnect = auto_reconnect
        self.mc_rate = mc_rate
        self.pm_rate = pm_rate
        self.op_control = op_control
        self._connection_state = self.DISCONNECTED
        self.static_users = utils.UserData(users)
        self._dynamic_users = utils.UserData()
        self._queues = [queue.Queue(), queue.Queue()]
        #self._timers = [utils.RepeatingTimer(), utils.RepeatingTimer()]

    def _get_con_state(self):
        """Returns a text representation of the connection state"""
        if self._connection_state == self.DISCONNECTED:
            return "D/C"
        elif self._connection_state == self.CONNECTING:
            return "CNTNG"
        elif self._connection_state == self.CONNECTED:
            return "CNTED"
        else:
            return "???"
        
    def _set_links(self, myID, links):
        """Set the links (property method)"""
        self._links = []
        self.add_links(myID, links)

    def _get_links(self):
        """Get the links (property method)"""
        return self._links

    def del_links (self, links):
        """Stops the connection from broadcasting to the specified link(s)"""
        if not isinstance(links, list):
            raise TypeError("Links specified must be in a list")
        self._links[:] = [t for t in self._links if t not in links]
            
    def add_links(self, myID, links):
        """
        Adds connection(s) to broadcast to.
        Links can be a string or a list of strings identifying connections
        """
        if not isinstance(links, list):
            raise TypeError("Links specified must be in a list")
        for x in links:
            #not already added and valid link
            if x != myID and x not in self._links and (x in self._program.connections):
                self._links.append(x)
            else:
                logger.warning("Link {} not added (already added or invalid)".format(x))

    def user_perm (self, nick, perm):
        """Check permissions on the user"""
        temp = self.static_users.attr(nick, perm)
        #set to true or (unset and (not looking at OP attribute or are and they have control) and dynamicly assigned permission)
        return temp == UserData.YES or (temp == UserData.UNSET and
                                       (perm != UserData.CTRL or self.op_control) and
                                       self._dynamic_users.attr(nick, perm) == UserData.YES)

    def _broadcast_message(self, nick, text, fmt):
        """
        Broadcasts a message to other links.
        Format string should have {0} and {1} in it for nick and message respectively
        """
        
        #Apply formatting and unescape text
        #(recieving link will escape it according to connection type)
        msg = self._unescape(fmt.format(nick, text))

        #to store invalid links
        del_links = []

        #send message to all links
        for target in self._links:
            if (target in self._program.connections):
                self._program.connections[target].send_chat(msg)
            else:
                del_links.append(target)
                logger.error("Tried to send message to a link that doesn't exist (deleting it)")

        #delete invalid links
        for x in del_links:
            del self._links[x]

    def _process_queue(self, num):
        """
        Sends a message in the chat/pm queue to the link.
        Messages are assumed to be fully formatted, escaped and converted to bytes
        """
        
        #TODO: time check when called/call from timer
        if not num in [self.MAIN, self.PM]:
            raise ValueError("Invalid queue number")
        
        if self._queues[num].qsize() == 0:
            return False
        try:
            line = self._queues[num].get_nowait()   
        except queue.Empty as e:
            return False

        if not isinstance(line, bytes):
            raise ValueError("Queued messages must have already been encoded to bytes")

        #TODO: send bytes to socket

    def join(self, timeout=None):
        """Override join to close all connections and wait until the thread terminates"""
        #TODO: disconnecting and closing connections
        super(Link, self).join(timeout)

    #set property
    links = property(_get_links, _set_links)
    connection_state = property(_get_con_state)

##################################################################################################
class DC (Link):
    """Superclass for all DC hub connections"""

    def __init__(self, program, server, nick, passwd, prefix, links, share, slots, client, auto_connect, auto_reconnect,
                 mc_rate, pm_rate, op_control, users):

        super(DC, self).__init__(program, server, nick, passwd, prefix, links, auto_connect, auto_reconnect, mc_rate, pm_rate, op_control, users)

        if type(self) == DC:
            raise Exception("DC must be subclassed")
        
        self.share = share
        self.slots = slots
        self.client = client

    def send_chat(self, text):
        """Sends a message to the mainchat queue"""
        #escape and format the message
        text = self._escape(text)
        msg = self._mc_format.format(self.nick, text)

        #encode and add to queue
        self.queues[self.MAIN].put_nowait(msg.encode(self._encoding, "replace"))
    
    def send_PM (self, text, user):
        """
        Sends a private message to the PM queue
        For ADC links, the parameter is the SID of the user, not the nick
        """
        #escape and format the message
        text = self._escape(text)
        msg = self._pm_format.format(user, self._myID(), text)

        #encode and add to queue
        self.queues[self.PM].put_nowait(msg.encode(self._encoding, "replace")) 

        
##################################################################################################
class NMDC (DC):
    """For connecting to NMDC hubs"""

    def __init__(self, program, server, nick, passwd, prefix, links = [], share = "10737418240", slots = "5", client = "CrossChatLink",
                 auto_connect = True, auto_reconnect = True, mc_rate = 0, pm_rate = 0, op_control = True, users = None):
        logging.debug("Configuring a new NMDC link")
        
        super(NMDC, self).__init__(program, server, nick, passwd, prefix, links, share, slots, client, auto_connect, auto_reconnect,
                 mc_rate, pm_rate, op_control, users)

        #formatting constants
        self._mc_format = "<{0}> {1}|" #to/msg
        self._pm_format = "$To: {0} From: {1} $<{1}> {2}|" #to/from/msg
        self._encoding = "cp1252"
        #escape translator
        self._escape_map = str.maketrans({0: "&#0;", # NULL
                                         5: "&#5;", # ENQ
                                         36: "&#36;", #$
                                         124: "&#124;"}) #|

    def _ID():
        """The ID of the bot (ADC = SID, NMDC = nick)"""
        return self.nick

    def _escape(self, msg):
        """Returns an escaped version of msg"""
        #TODO: test this works (issues with spaces at least)
        return temp.translate(self._escape_map)

    def _unescape(self, msg):
        """Returns an unescaped version of msg"""
        msg = msg.replace("&#0;", chr(0))
        msg = msg.replace("&#5;", chr(5))
        msg = msg.replace("&#36", chr(36))
        msg = msg.replace("&#124;", chr(124))
        return msg
    
    def _parse_line(self, line):
        """Parses a line recived from the server"""
        #TODO: Implement NMDC protocol
        pass

    def run(self):
        logging.info("NMDC thread initilized")
        #TODO: connect, recieve, and process data


##################################################################################################
class ADC (DC):
    """For connecting to ADC hubs"""

    _delim = "\n"
    
    def __init__(self, program, server, nick, passwd, prefix, links = [], share = "10737418240", slots = "5", client = "CrossChatLink",
                 auto_connect = True, auto_reconnect = True, mc_rate = 0, pm_rate = 0, op_control = True, users = None):
        logging.debug("Configuring a new ADC link")
        
        super(ADC, self).__init__(program, server, nick, passwd, prefix, links, share, slots, client, auto_connect, auto_reconnect,
                 mc_rate, pm_rate, op_control, users)

        #formatting constants
        self._mc_format = "BMSG {0} {1}\n" #to/msg
        self._pm_format = "DMSG {1} {0} {2} PM{1}\n" #to/from/msg
        self._encoding = "utf-8"

        self._user_SIDs = dict()
        self._SID = None

    def _ID():
        """The ID of the bot (ADC = SID, NMDC = nick)"""
        return self._SID

    def _escape(self, msg):
        """Returns an escaped version of msg"""
        #TODO: str.translate()?
        msg = msg.replace("\\", "\\\\")
        msg = msg.replace("\n", "\\n")
        msg = msg.replace(" ", "\\s")
        return msg

    def _unescape(self, msg):
        """Returns an unescaped version of msg"""
        return utils.escape_replace(msg, "\\", {"\\": "\\\\", "s": " ", "n": "\n"})
        
    def _parse_line(self, line):
        """Parses a line recived from the server"""
        #TODO: Implement ADC protocol
        pass
    
    def run(self):
        logging.info("ADC thread initilized")
        #TODO: connect, recieve, and process data

##################################################################################################
class IRC (Link):

    def __init__(self, program, server, nick, passwd, prefix, links = [], ident_text = "CrossChatLink", channels = "", connect_cmds = [], auto_connect = True, auto_reconnect = True,
                 mc_rate = 0, pm_rate = 0, op_control = True, users = None):
        logging.debug("Configuring a new IRC link")
        
        super(IRC, self).__init__(program, server, nick, passwd, prefix, links, auto_connect, auto_reconnect, mc_rate, pm_rate, op_control, users)

        self.ident_text = ident_text
        self.channels = channels
        self.connect_cmds = connect_cmds

        #formatting constants
        self._mc_format = "PRIVMSG {0} :{1}\r\n" #channel(s)/msg
        self._pm_format = "PRIVMSG {0} :{1}\r\n" #to/msg
        self._encoding = "utf-8"

    def send_chat(self, text):
        """Sends a message to the mainchat queue"""
        #Split multiline messages
        msgs = text.split("\r\n")
        
        for msg in msgs:
            #escape and format the message
            text = self._escape(text)
            msg = self._mc_format.format(self._channels_no_keys(), text)

            #encode in ansi
            self.queues[self.MAIN].put_nowait(msg.encode(self._encoding, "replace"))
    
    def send_PM (self, text, user):
        """Sends a private message to the PM queue"""
        #Split multiline messages
        msgs = text.split("\r\n")
        
        for msg in msgs:
            #escape and format the message
            text = self._escape(text)
            msg = self._pm_format.format(user, text)

            #encode in ansi
            self.queues[self.PM].put_nowait(msg.encode(self._encoding, "replace"))

    def _channels_no_keys(self):
        """Returns a list of channels without the keys"""
        #done in one line just cause
        #splits by "#", trims spaces and commas, filters nulls out,
        #takes each element up to the first space and prefixes it with the "#"
        return ["#" + i.split(" ")[0] for i in [i.strip(" ,") for i in self.channels.split("#")] if i != ""]
        
    def _parseLine(self, line):
        """Parses a line recived from the server"""
        #TODO: Implement IRC protocol

    def run(self):
        logging.info("IRC thread initilized")
        #TODO: connect, recieve, and process data


