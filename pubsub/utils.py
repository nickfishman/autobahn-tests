from twisted.internet import reactor
from twisted.python import log

from autobahn.wamp import WampClientFactory

class AutoreconnectWampClientFactory(WampClientFactory):
   """Utility client factory that automatically reconnects on connection failures"""

   def _reconnect(self, connector):
      log.msg("reconnecting in 2 secs ..")
      reactor.callLater(2, connector.connect)

   # The next two methods are Twisted callbacks when a client factory loses its connection
   def clientConnectionLost(self, connector, reason):
      self.protocol = None
      self._reconnect(connector)

   def clientConnectionFailed(self, connector, reason):
      self.protocol = None
      self._reconnect(connector)