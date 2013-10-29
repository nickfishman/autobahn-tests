autobahn-tests
==============

Stress tests for Autobahn pubsub

Running
-------

First, run the Autobahn pubsub server:

    python pubsub/server.py

Then run the stress test client (in another terminal):

    python pubsub/stressclient.py

Test Results
------------
During the stress test, the client will output statistics about the current state of the test.
Afterwards, the client will output summary statistics, including any failures encountered.

Configuration
-------------
Most timeouts, quantities, and constants can be configured via optional command-line flags.

```
$ python pubsub/stressclient.py -h
usage: Client that floods an autobahn pubsub server with lots of messages
       [-h] [-m NUM_MESSAGES] [-s NUM_SENDERS] [-t TOPIC_URI]
       [-u WEBSOCKET_URL] [-r MAX_RUNTIME] [-d] [-l] [-i NUM_ITERATIONS]
       [--websocket_timeout WEBSOCKET_TIMEOUT]

optional arguments:
  -h, --help            show this help message and exit
  -m NUM_MESSAGES, --num_messages NUM_MESSAGES
                        number of messages each client will send (default:
                        100)
  -s NUM_SENDERS, --num_senders NUM_SENDERS
                        number of sender clients (default: 500)
  -t TOPIC_URI, --topic_uri TOPIC_URI
                        autobahn topic uri to use (default: http://autobahn-
                        pubsub/channels/1/stress)
  -u WEBSOCKET_URL, --websocket_url WEBSOCKET_URL
                        autobahn websocket url to use (default:
                        ws://localhost:9000)
  -r MAX_RUNTIME, --max_runtime MAX_RUNTIME
                        maximum test timeout (in seconds) (default: 30)
  -d, --debug           whether to enable debugging (requires --log_autobahn)
                        (default: False)
  -l, --log_autobahn    whether to enable autobahn logging (default: False)
  -i NUM_ITERATIONS, --num_iterations NUM_ITERATIONS
                        number of batches to perform (default: 1)
  --websocket_timeout WEBSOCKET_TIMEOUT
                        websocket connection timeout (default: 30)
```

Running multiple stress tests simultaneously
--------------------------------------------
You can run multiple stress test clients in different terminals to increase the load.
Be sure to use a distinct topic uri (```--topic_uri```) for each client. By default, the topic
URI must start with ```http://autobahn-pubsub/channels/```, although this can be modified when running
server.py (```--base_uri```).

This will run 3 stress clients, each using distinct topic URIs.
```
terminal1$ python pubsub/server.py
...
terminal2$ python pubsub/stressclient.py -t http://autobahn-pubsub/channels/1/stress -i 1000
...
terminal3$ python pubsub/stressclient.py -t http://autobahn-pubsub/channels/2/stress -i 1000
...
terminal4$ python pubsub/stressclient.py -t http://autobahn-pubsub/channels/3/stress -i 1000
```

