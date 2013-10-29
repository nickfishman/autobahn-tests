import sys

from twisted.python import log
from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.static import File

from autobahn.websocket import listenWS
from autobahn.wamp import WampServerFactory, \
                          WampServerProtocol

BASE_URI = "http://autobahn-pubsub/channels/"

class PubSubServer(WampServerProtocol):

   def onSessionOpen(self):
      self.registerForPubSub(BASE_URI, True)

if __name__ == '__main__':
   log.startLogging(sys.stdout)
   debug = len(sys.argv) > 1 and sys.argv[1] == 'debug'

   factory = WampServerFactory("ws://localhost:9000", debugWamp = debug)
   factory.protocol = PubSubServer
   factory.setProtocolOptions(allowHixie76 = True)
   listenWS(factory)

   webdir = File(".")
   web = Site(webdir)
   reactor.listenTCP(8080, web)

   reactor.run()