---
title: Subscribe and unsubscribe
description: Learn more about how to subscribe to and unsubscribe from topics using Amplify's PubSub category
---

## Subscribe

### Subscribe to a topic

In order to start receiving messages from your provider, you need to subscribe to a topic as follows;

```javascript
pubsub.subscribe({ topics: 'myTopic' }).subscribe({
  next: (data) => console.log('Message received', data),
  error: (error) => console.error(error),
  complete: () => console.log('Done')
});
```

Following events will be triggered with `subscribe()`

| Event | Description |
| :-: | --- |
| `next` | Triggered every time a message is successfully received for the topic |
| `error` | Triggered when subscription attempt fails |
| `complete` | Triggered when you unsubscribe from the topic |

### Subscribe to multiple topics

To subscribe for multiple topics, just pass a String array including the topic names:

```javascript
pubsub.subscribe({ topics: ['myTopic1', 'myTopic1'] }).subscribe({
  //...
});
```

## Unsubscribe

To stop receiving messages from a topic, you can use `unsubscribe()` method:

```javascript
const sub1 = pubsub.subscribe({ topics: 'myTopicA' }).subscribe({
  next: (data) => console.log('Message received', data),
  error: (error) => console.error(error),
  complete: () => console.log('Done')
});

sub1.unsubscribe();
// You will no longer get messages for 'myTopicA'
```

## Subscription connection status updates

Now that your application is setup and using pubsub subscriptions, you may want to know when the subscription is finally established, or reflect to your users when the subscription isn't healthy. You can monitor the connection state for changes via Hub.

```typescript
import { CONNECTION_STATE_CHANGE, ConnectionState } from '@aws-amplify/pubsub';
import { Hub } from 'aws-amplify/utils';

Hub.listen('pubsub', (data: any) => {
  const { payload } = data;
  if (payload.event === CONNECTION_STATE_CHANGE) {
    const connectionState = payload.data.connectionState as ConnectionState;
    console.log(connectionState);
  }
});
```

#### Connection states

- **`Connected`** - Connected and working with no issues.
- **`ConnectedPendingDisconnect`** - The connection has no active subscriptions and is disconnecting.
- **`ConnectedPendingKeepAlive`** - The connection is open, but has missed expected keep alive messages.
- **`ConnectedPendingNetwork`** - The connection is open, but the network connection has been disrupted. When the network recovers, the connection will continue serving traffic.
- **`Connecting`** - Attempting to connect.
- **`ConnectionDisrupted`** - The connection is disrupted and the network is available.
- **`ConnectionDisruptedPendingNetwork`** - The connection is disrupted and the network connection is unavailable.
- **`Disconnected`** - Connection has no active subscriptions and is disconnecting.

### Connection issues and automated reconnection

Your application can lose connectivity for any number of reasons such as network outages or when the device is put to sleep. Your subscriptions will automatically reconnect when it becomes possible to do so.

While offline, your application will miss messages and will not automatically catch up when reconnection happens. Depending on your usecase, you may want take action to catch up when your app comes back online.

```typescript
const fetchRecentData = () => {
  // Retrieve recent data from some sort of data storage service
}

let priorConnectionState: ConnectionState;

Hub.listen("pubsub", (data: any) => {
  const { payload } = data;
  if (
    payload.event === CONNECTION_STATE_CHANGE
  ) {

    if (priorConnectionState === ConnectionState.Connecting && payload.data.connectionState === ConnectionState.Connected) {
      fetchRecentData();
    }
    priorConnectionState = payload.data.connectionState;
  }
});

pubsub.subscribe('myTopic').subscribe({
  next: data => // Process incoming messages
})
```
