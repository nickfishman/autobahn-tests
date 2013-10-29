import sys
import random
from datetime import datetime

from twisted.python import log
from twisted.internet import reactor, task

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory, \
                                  WampClientProtocol

from utils import AutoreconnectWampClientFactory

CHANNEL_IDS = []
BASE_URI = "http://autobahn-pubsub/channels/%s/stress"
NUM_MESSAGES = 100
NUM_SENDERS = 500
BATCH_STATES = ("UNSTARTED", "ACTIVE", "DONE")
MAX_RUNTIME = 30

class SenderClientProtocol(WampClientProtocol):
    """Client protocol that connects and publishes a certain number of messages
    on a given channel."""

    def __init__(self, clientId, factory):
        # WampClientProtocol has no __init__ method
        self.clientId = clientId
        self.factory = factory

    def onSessionOpen(self):
        # TODO(nf): Extend this stress test to use multiple channels
        for channel_id in CHANNEL_IDS:
            uri = BASE_URI % channel_id
            for i in xrange(NUM_MESSAGES):
                self.publish(uri, {
                    "number": random.random(),
                    "clientId": self.clientId
                })

class SenderClientFactory(WampClientFactory):

    def __init__(self, app, clientId):
        WampClientFactory.__init__(self, app.url, app.debugWamp)
        self.protocol = None
        self.app = app
        self.clientId = clientId
        self.failureRecorded = False

    def buildProtocol(self, addr):
        # Allow our ClientProtocol to reference this factory, for debugging
        self.protocol = SenderClientProtocol(clientId=self.clientId, factory=self)
        return self.protocol

    def handleError(self, destination_list, reason):
        """Handle an error and record our client_id into the appropriate list"""
        if not self.failureRecorded and app.state == "ACTIVE":
            self.failureRecorded = True
            destination_list.append(self.clientId)
            short_error = str(reason)
            app.errors[short_error] = app.errors.get(short_error, 0) + 1

        self.protocol = None

    def clientConnectionLost(self, connector, reason):
        self.handleError(app.connectionsLost, reason)

    def clientConnectionFailed(self, connector, reason):
        self.handleError(app.connectionsFailed, reason)

class MonitorClientProtocol(WampClientProtocol):
    """Monitor protocol that subscribes on a given channel and records received data
    into a global statistics object."""

    def __init__(self, clientId, factory):
        # WampClientProtocol has no __init__ method
        self.clientId = clientId
        self.factory = factory
        self.app = self.factory.app

    def onSessionOpen(self):
        for channel_id in CHANNEL_IDS:
            uri = BASE_URI % channel_id
            self.subscribe(uri, self.onEvent)

    def onEvent(self, topicUri, event):
        clientId = event["clientId"]

        app.numReceived += 1
        numReceivedPerClient = app.numReceivedPerClient
        numReceivedPerClient[clientId] = numReceivedPerClient.get(clientId, 0) + 1

class MonitorClientFactory(AutoreconnectWampClientFactory):

    def __init__(self, app, clientId):
        WampClientFactory.__init__(self, app.url, app.debugWamp)
        self.protocol = None
        self.app = app
        self.clientId = clientId

    def buildProtocol(self, addr):
        self.protocol = MonitorClientProtocol(clientId=self.clientId, factory=self)
        return self.protocol

class App(object):

    def init_batch(self):
        print "BATCH STARTED"

        self.numReceived = 0
        self.numReceivedPerClient = {}
        self.connectionsLost = []
        self.connectionsFailed = []
        self.state = "ACTIVE"
        self.startTime = datetime.now()
        self.check_batchTask = task.LoopingCall(self.check_batch)
        self.check_batchTask.start(1.0)
        self.lastResortCall = reactor.callLater(MAX_RUNTIME, self.terminate_batch)
        self.errors = {}
        self.senders = []

        for i in xrange(NUM_SENDERS):
            sender = SenderClientFactory(self, clientId=i)
            connectWS(sender, timeout=15)
            self.senders.append(sender)

    def check_batch(self):
        if self.numReceived == self.current_expected_total():
            self.complete_batch()
        else:
            self.print_statistics(verbose=False)

    def terminate_batch(self):
        print "BATCH EXCEEDED TIMEOUT, FORCING STOP"
        self.lastResortCall = None
        self.complete_batch()

    def complete_batch(self):
        print "BATCH COMPLETED"
        print datetime.now() - app.startTime

        self.check_batchTask.stop()
        if self.lastResortCall:
            self.lastResortCall.cancel()
        self.state = "DONE"
        self.print_statistics(verbose=True)

        print "BATCH CLEANUP"
        for sender in app.senders:
            if sender.protocol:
                sender.protocol.sendClose()
            sender.stopFactory()

        app.senders = []

    def get_complete_clients(self):
        """Return the list of client IDs whose messages we have received completely"""
        complete_clients = []
        for (client_id, num_received) in app.numReceivedPerClient.items():
            if num_received == NUM_MESSAGES:
                complete_clients.append(client_id)
        return complete_clients

    def get_incomplete_clients(self):
        """Return the list of client IDs whose messages we have NOT received completely"""
        incomplete_clients = []
        for (client_id, num_received) in app.numReceivedPerClient.items():
            if num_received != NUM_MESSAGES:
                incomplete_clients.append(client_id)
        return incomplete_clients

    def current_expected_total(self):
        """Return the total number of messages we're expecting to receive, taking
        into account any connection failures that we know of."""
        max_total = NUM_SENDERS * NUM_MESSAGES

        # Messages that we'll never receive because client connections failed before sending them
        failed_messages = NUM_MESSAGES * (len(self.connectionsFailed) + len(self.connectionsLost))

        return max_total - failed_messages

    def print_statistics(self, verbose=True):
        print datetime.now() - self.startTime

        num_expected = NUM_MESSAGES * NUM_SENDERS
        if verbose:
            print "STATE: %s" % self.state
            print "MESSAGE DELIVERY STATISTICS"
            print "\t Messages expected: %d" % num_expected
        print "\t Messages expected (adjusted for failures): %d" % self.current_expected_total()

        num_received = self.numReceived
        num_received_percent = num_received / float(num_expected) * 100
        print "\t Messages received: %d (%s%%)" % (num_received, num_received_percent)

        incomplete_clients = self.get_incomplete_clients()
        complete_clients = self.get_complete_clients()
        if verbose:
            print "CLIENT CONNECTION STATISTICS"
            print "\t Attempted clients: %d" % NUM_SENDERS
            print "\t Clients which missed some messages: %d (%s%%)" % \
                    (len(incomplete_clients), float(len(incomplete_clients)) / NUM_SENDERS * 100)
        print "\t Clients which sent all messages: %d (%s%%)" % \
                (len(complete_clients), float(len(complete_clients)) / NUM_SENDERS * 100)

        failed_clients = self.connectionsFailed + self.connectionsLost
        print "\t Clients which experienced connection failures: %s (%s%%)" % \
                (len(failed_clients), float(len(failed_clients)) / NUM_SENDERS * 100)
        if verbose:
            print "\t\t Connections lost: %s" % len(self.connectionsLost)
            print "\t\t Connections failed: %s" % len(self.connectionsFailed)

        unknown_clients = set(xrange(NUM_SENDERS)) - set(failed_clients) - set(incomplete_clients) - set(complete_clients)
        if unknown_clients and verbose:
            print "\t Clients unaccounted for: %s (%s%%)" % \
                    (len(unknown_clients), float(len(unknown_clients)) / NUM_SENDERS * 100)
            print "\t\t Client IDs: %s" % sorted(list(unknown_clients))

        if verbose:
            print "ERROR INFORMATION:"
            for (error_type, count) in app.errors.items():
                print "\t[%d] %s" % (count, error_type)

        print ""

if __name__ == '__main__':
    if len(sys.argv) > 1:
        CHANNEL_IDS = sys.argv[1].split(",")
    else:
        CHANNEL_IDS = ['11']
    print "USING CHANNELS %s" % CHANNEL_IDS

    #log.startLogging(sys.stdout)

    app = App()
    app.url = "ws://localhost:9000"
    app.debugWamp = False

    monitor = MonitorClientFactory(app, clientId="Monitor")
    app.monitor = monitor
    connectWS(monitor)

    reactor.callLater(2, app.init_batch)

    reactor.run()
