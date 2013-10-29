import argparse
import random
import sys

from datetime import datetime

from twisted.python import log
from twisted.internet import reactor, task

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory, \
                                  WampClientProtocol

from utils import AutoreconnectWampClientFactory

parser = argparse.ArgumentParser(
    "Client that floods an autobahn pubsub server with lots of messages",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-m", "--num_messages", type=int, help="number of messages each client will send", default=100)
parser.add_argument("-s", "--num_senders", type=int, help="number of sender clients", default=500)
parser.add_argument("-t", "--topic_uri", type=str, help="autobahn topic uri to use", default="http://autobahn-pubsub/channels/1/stress")
parser.add_argument("-u", "--websocket_url", type=str, help="autobahn websocket url to use", default="ws://localhost:9000")
parser.add_argument("-r", "--max_runtime", type=int, help="maximum test timeout (in seconds)", default=30)
parser.add_argument("-d", "--debug", action='store_true', help="whether to enable debugging (requires --log_autobahn)", default=False)
parser.add_argument("-l", "--log_autobahn", action='store_true', help="whether to enable autobahn logging", default=False)
parser.add_argument("-i", "--num_iterations", type=int, help="number of batches to perform", default=1)
parser.add_argument("--websocket_timeout", type=int, help="websocket connection timeout (in seconds)", default=30)

ARGS = parser.parse_args()


class SenderClientProtocol(WampClientProtocol):
    """Client protocol that connects and publishes a certain number of messages
    on a given channel."""

    def __init__(self, clientId, factory):
        # WampClientProtocol has no __init__ method
        self.clientId = clientId
        self.factory = factory

    def onSessionOpen(self):
        self.publish_bundle()

    def publish_bundle(self):
        # TODO(nf): Extend this stress test to use multiple channels
        uri = ARGS.topic_uri
        for i in xrange(ARGS.num_messages):
            self.publish(uri, {
                "number": random.random(),
                "clientId": self.clientId
            })

class SenderClientFactory(WampClientFactory):

    def __init__(self, app, clientId):
        WampClientFactory.__init__(self, ARGS.websocket_url, ARGS.debug)
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
        uri = ARGS.topic_uri
        self.subscribe(uri, self.onEvent)

    def onEvent(self, topicUri, event):
        clientId = event["clientId"]

        app.numReceived += 1
        numReceivedPerClient = app.numReceivedPerClient
        numReceivedPerClient[clientId] = numReceivedPerClient.get(clientId, 0) + 1

class MonitorClientFactory(AutoreconnectWampClientFactory):

    def __init__(self, app, clientId):
        WampClientFactory.__init__(self, ARGS.websocket_url, ARGS.debug)
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
        if app.iteration == 0:
            # Don't reset data on failed connections between iterations
            # In the future this could be configurable via a flag
            self.connectionsLost = []
            self.connectionsFailed = []

        # Either "ACTIVE" or "DONE"
        self.state = "ACTIVE"
        self.startTime = datetime.now()
        self.check_batchTask = task.LoopingCall(self.check_batch)
        self.check_batchTask.start(1.0)
        self.lastResortCall = reactor.callLater(ARGS.max_runtime, self.terminate_batch)
        self.errors = {}
        if app.iteration == 0:
            self.senders = []

            for i in xrange(ARGS.num_senders):
                sender = SenderClientFactory(self, clientId=i)
                connectWS(sender, timeout=ARGS.websocket_timeout)
                self.senders.append(sender)
        else:
            # Reuse senders between iterations (except for those that failed)
            for sender in self.senders:
                if sender.protocol:
                    sender.protocol.publish_bundle()

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

        if app.iteration == ARGS.num_iterations - 1:
            print "BATCH CLEANUP"
            for sender in app.senders:
                if sender.protocol:
                    sender.protocol.sendClose()
                sender.stopFactory()

            app.senders = []
            reactor.stop()
        else:
            app.iteration += 1
            print "MOVING ON TO ITERATION %d" % app.iteration
            reactor.callLater(2, app.init_batch)

    def get_complete_clients(self):
        """Return the list of client IDs whose messages we have received completely"""
        complete_clients = []
        for (client_id, num_received) in app.numReceivedPerClient.items():
            if num_received == ARGS.num_messages:
                complete_clients.append(client_id)
        return complete_clients

    def get_incomplete_clients(self):
        """Return the list of client IDs whose messages we have NOT received completely"""
        incomplete_clients = []
        for (client_id, num_received) in app.numReceivedPerClient.items():
            if num_received != ARGS.num_messages:
                incomplete_clients.append(client_id)
        return incomplete_clients

    def current_expected_total(self):
        """Return the total number of messages we're expecting to receive, taking
        into account any connection failures that we know of."""
        max_total = ARGS.num_senders * ARGS.num_messages

        # Messages that we'll never receive because client connections failed before sending them
        failed_messages = ARGS.num_messages * (len(self.connectionsFailed) + len(self.connectionsLost))

        return max_total - failed_messages

    def print_statistics(self, verbose=True):
        print datetime.now() - self.startTime

        num_expected = ARGS.num_messages * ARGS.num_senders
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
            print "\t Attempted clients: %d" % ARGS.num_senders
            print "\t Clients which missed some messages: %d (%s%%)" % \
                    (len(incomplete_clients), float(len(incomplete_clients)) / ARGS.num_senders * 100)
        print "\t Clients which sent all messages: %d (%s%%)" % \
                (len(complete_clients), float(len(complete_clients)) / ARGS.num_senders * 100)

        failed_clients = self.connectionsFailed + self.connectionsLost
        print "\t Clients which experienced connection failures: %s (%s%%)" % \
                (len(failed_clients), float(len(failed_clients)) / ARGS.num_senders * 100)
        if verbose and (self.connectionsLost or self.connectionsFailed):
            print "\t\t Connections lost: %s" % len(self.connectionsLost)
            print "\t\t Connections failed: %s" % len(self.connectionsFailed)

        unknown_clients = set(xrange(ARGS.num_senders)) - set(failed_clients) - set(incomplete_clients) - set(complete_clients)
        if unknown_clients and verbose:
            print "\t Clients unaccounted for: %s (%s%%)" % \
                    (len(unknown_clients), float(len(unknown_clients)) / ARGS.num_senders * 100)
            print "\t\t Client IDs: %s" % sorted(list(unknown_clients))

        if verbose and app.errors:
            print "ERROR INFORMATION:"
            for (error_type, count) in app.errors.items():
                print "\t[%d] %s" % (count, error_type)

        print ""
        # TODO(nf): log average # of messages received per second

if __name__ == '__main__':
    if ARGS.log_autobahn:
        log.startLogging(sys.stdout)

    app = App()

    monitor = MonitorClientFactory(app, clientId="Monitor")
    app.monitor = monitor
    app.iteration = 0
    connectWS(monitor)

    reactor.callLater(1, app.init_batch)

    reactor.run()
