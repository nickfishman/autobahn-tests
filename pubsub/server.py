import argparse
import sys

from twisted.python import log
from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.static import File

from autobahn.websocket import listenWS
from autobahn.wamp import WampServerFactory, \
                          WampServerProtocol

parser = argparse.ArgumentParser(
    "Basic autobahn pubsub server",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-b", "--base_uri", type=str, help="autobahn prefix uri to use", default="http://autobahn-pubsub/channels/")
parser.add_argument("-d", "--debug", action='store_true', help="whether to enable debugging", default=False)
parser.add_argument("-u", "--websocket_url", type=str, help="autobahn websocket url to use", default="ws://localhost:9000")

ARGS = parser.parse_args()

class PubSubServer(WampServerProtocol):

   def onSessionOpen(self):
      self.registerForPubSub(ARGS.base_uri, True)

if __name__ == '__main__':
   log.startLogging(sys.stdout)

   factory = WampServerFactory(ARGS.websocket_url, debugWamp=ARGS.debug)
   factory.protocol = PubSubServer
   factory.setProtocolOptions(allowHixie76 = True)
   listenWS(factory)

   webdir = File(".")
   web = Site(webdir)
   reactor.listenTCP(8080, web)

   reactor.run()