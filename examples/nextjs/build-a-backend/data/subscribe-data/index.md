---
title: Subscribe to real-time events
description: Set up real-time data subscriptions in your app to get live updates, filter those subscriptions on the server side, and unsubscribe when no longer needed.
---

In this guide, we will outline the benefits of enabling real-time data integrations and how to set up and filter these subscriptions. We will also cover how to unsubscribe from subscriptions.

Before you begin, you will need:

- An [application connected to the API](/[platform]/build-a-backend/data/connect-to-API/)
- Data already created to modify

> [!WARNING]
> With Amplify Data Construct `@aws-amplify/data-construct@1.8.4`
>       , an improvement was made to how relational field data is handled in
>       subscriptions when different authorization rules apply to related models
>       in a schema. The improvement redacts the values for the relational fields,
>       displaying them as null or empty, to prevent unauthorized access to
>       relational data.
>
>       This redaction occurs whenever it cannot be determined that the child
>       model will be protected by the same permissions as the parent model.
>
>       Because subscriptions are tied to mutations and the selection set provided
>       in the result of a mutation is then passed through to the subscription,
>       relational fields in the result of mutations must be redacted.
>
>       If an authorized end-user needs access to the redacted relational fields,
>       they should perform a query to read the relational data.
>
>       Additionally, subscriptions will inherit related authorization when
>       relational fields are set as required. To better protect relational data,
>       consider modifying the schema to use optional relational fields.

## Set up a real-time list query

The recommended way to fetch a list of data is to use `observeQuery` to get a real-time list of your app data at all times. You can integrate `observeQuery` with React's `useState` and `useEffect` hooks in the following way:

```ts
import { useState, useEffect } from 'react';
import { generateClient } from 'aws-amplify/data';
import type { Schema } from '../amplify/data/resource';

type Todo = Schema['Todo']['type'];

const client = generateClient<Schema>();

export default function MyComponent() {
  const [todos, setTodos] = useState<Todo[]>([]);

  useEffect(() => {
    const sub = client.models.Todo.observeQuery().subscribe({
      next: ({ items, isSynced }) => {
        setTodos([...items]);
      },
    });
    return () => sub.unsubscribe();
  }, []);

  return (
    <ul>
      {todos.map((todo) => (
        <li key={todo.id}>{todo.content}</li>
      ))}
    </ul>
  );
}
```

`observeQuery` fetches and paginates through all of your available data in the cloud. While data is syncing from the cloud, snapshots will contain all of the items synced so far and an `isSynced` status of `false`. When the sync process is complete, a snapshot will be emitted with all the records in the local store and an `isSynced` status of `true`.

<Accordion title='Missing real-time events and model fields' headingLevel='4' eyebrow='Troubleshooting'>

If you don't see all of the real-time events and model fields you expect to see, here are a few things to look for.

#### Authorization

The model's [authorization rules](/[platform]/build-a-backend/data/customize-authz/) must grant the appropriate rights to the user.

| Operation | Authorization |
| -- | -- |
| `onCreate` | `read` OR `listen` |
| `onUpdate` | `read` OR `listen` |
| `onDelete` | `read` OR `listen` |
| `observeQuery` | `read` OR (`listen` AND `list`) |

If the authorization rules are correct, also ensure the session is authenticated as expected.

#### Selection Set Parity

All of the fields you expect to see in a real-time update must be present in the selection set of the **mutation** that triggers it. A mutation essentially "provides" the fields via its selection set that the corresponding subscription can then select from.

One way to address this is to use a common selection set variable for both operations. For example:

```ts
// Defining your selection set `as const` ensures the types
// propagate through to the response objects.
const selectionSet = ['title', 'author', 'posts.*'] as const;

const sub = client.models.Blog.observeQuery(
  filter: { id: { eq: 'blog-id' } },
  selectionSet: [...selectionSet]
).subscribe({
  next(data) {
    handle(data.items)
  }
});

// The update uses the same selection set, ensuring all the
// required fields are provided to the subscriber.
const { data } = await client.models.Blog.update({
  id: 'blog-id',
  name: 'Updated Name'
}, {
  selectionSet: [...selectionSet]
});
```

This works well if all subscriptions to `Blog` require the same subset of fields. If multiple subscriptions are involved with various selection sets, you must ensure that all `Blog` mutations contain the superset of fields from all subscriptions.

Alternatively, you can skip the custom selection sets entirely. The internally generated selection set for any given model is identical across operations by default. The trade-off is that the default selection sets exclude related models. So, when related models are required, you would need to either lazy load them or construct a query to fetch them separately.

#### Related Model Mutations

Mutations do not trigger real-time updates for *related* models. This is true even when the subscription includes a related model in the selection set. For example, if we're subscribed to a particular `Blog` and wish to see updates when a `Post` is added or changed, it's tempting to create  a subscribe on `Blog` and assume it "just works":

```ts
// Notice how we're fetching a few `Blog` details, but mostly using
// the selection set to grab all the related posts.
const selectionSet = ['title', 'author', 'posts.*'] as const;

const sub = client.models.Blog.observeQuery(
  filter: { id: { eq: 'blog-id' } },
  selectionSet: [...selectionSet]
).subscribe({
  next(data) {
    handle(data.items)
  }
});
```

But, mutations on `Post` records won't trigger an real-time event for the related `Blog`. If you need `Blog` updates when a `Post` is added, you must manually "touch" the relevant `Blog` record.

```ts
async function addPostToBlog(
  post: Schema['Post']['createType'],
  blog: Schema['Blog']['type']
) {
  // Create the post first.
  await client.models.Post.create({
    ...post,
    blogId: blog.id
  });

  // "Touch" the blog, notifying subscribers to re-render.
  await client.models.Blog.update({
    id: blog.id
  }, {
    // Remember to include the selection set if the subscription
    // is looking for related-model fields!
    selectionSet: [...selectionSet]
  });
}
```

</Accordion>

## Set up a real-time event subscription

Subscriptions is a feature that allows the server to send data to its clients when a specific event happens. For example, you can subscribe to an event when a new record is created, updated, or deleted through the API. Subscriptions are automatically available for any `a.model()` in your Amplify Data schema.

```ts
import { generateClient } from 'aws-amplify/data';
import type { Schema } from '../amplify/data/resource';

const client = generateClient<Schema>();

// Subscribe to creation of Todo
const createSub = client.models.Todo.onCreate().subscribe({
  next: (data) => console.log(data),
  error: (error) => console.warn(error),
});

// Subscribe to update of Todo
const updateSub = client.models.Todo.onUpdate().subscribe({
  next: (data) => console.log(data),
  error: (error) => console.warn(error),
});

// Subscribe to deletion of Todo
const deleteSub = client.models.Todo.onDelete().subscribe({
  next: (data) => console.log(data),
  error: (error) => console.warn(error),
});

// Stop receiving data updates from the subscription
createSub.unsubscribe();
updateSub.unsubscribe();
deleteSub.unsubscribe();
```

## Set up server-side subscription filters

Subscriptions take an optional `filter` argument to define service-side subscription filters:

```ts
import { generateClient } from 'aws-amplify/data';
import type { Schema } from '../amplify/data/resource';

const client = generateClient<Schema>();

const sub = client.models.Todo.onCreate({
  filter: {
    content: {
      contains: 'groceries',
    },
  },
}).subscribe({
  next: (data) => console.log(data),
  error: (error) => console.warn(error),
});
```

If you want to get all subscription events, don't specify any `filter` parameters.

<Callout>

**Limitations:**

- Specifying an empty object `{}` as a filter is **not** recommended. Using `{}` as a filter might cause inconsistent behavior based on your data model's authorization rules.
- If you're using dynamic group authorization and you authorize based on a single group per record, subscriptions are only supported if the user is part of five or fewer user groups.
- Additionally, if you authorize by using an array of groups (`groups: [String]`),
  - subscriptions are only supported if the user is part of 20 or fewer groups
  - you can only authorize 20 or fewer user groups per record

</Callout>

### Subscription connection status updates

Now that your application is set up and using subscriptions, you may want to know when the subscription is finally established, or reflect to your users when the subscription isn't healthy. You can monitor the connection state for changes through the `Hub` local eventing system.

```ts
import { CONNECTION_STATE_CHANGE, ConnectionState } from 'aws-amplify/data';
import { Hub } from 'aws-amplify/utils';

Hub.listen('api', (data: any) => {
  const { payload } = data;
  if (payload.event === CONNECTION_STATE_CHANGE) {
    const connectionState = payload.data.connectionState as ConnectionState;
    console.log(connectionState);
  }
});
```

#### Subscription connection states

- **`Connected`** - Connected and working with no issues.
- **`ConnectedPendingDisconnect`** - The connection has no active subscriptions and is disconnecting.
- **`ConnectedPendingKeepAlive`** - The connection is open, but has missed expected keep-alive messages.
- **`ConnectedPendingNetwork`** - The connection is open, but the network connection has been disrupted. When the network recovers, the connection will continue serving traffic.
- **`Connecting`** - Attempting to connect.
- **`ConnectionDisrupted`** - The connection is disrupted and the network is available.
- **`ConnectionDisruptedPendingNetwork`** - The connection is disrupted and the network connection is unavailable.
- **`Disconnected`** - Connection has no active subscriptions and is disconnecting.

<Accordion title='Troubleshoot connection issues and automated reconnection' headingLevel='4' eyebrow='Troubleshooting'>

Connections between your application and backend subscriptions can be interrupted for various reasons, including network outages or the device entering sleep mode. Your subscriptions will automatically reconnect when it becomes possible to do so.

While offline, your application will miss messages and will not automatically catch up when reconnected. Depending on your use case, you may want to take action for your app to catch up when it comes back online.

```js
import { generateClient, CONNECTION_STATE_CHANGE, ConnectionState } from 'aws-amplify/data'
import { Hub } from 'aws-amplify/utils'
import { Schema } from '../amplify/data/resource';

const client = generateClient<Schema>()

const fetchRecentData = () => {
  const { data: allTodos } = await client.models.Todo.list();
}

let priorConnectionState: ConnectionState;

Hub.listen("api", (data: any) => {
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

const createSub = client.models.Todo.onCreate().subscribe({
  next: payload => // Process incoming messages
});

const updateSub = client.models.Todo.onUpdate().subscribe({
  next: payload => // Process incoming messages
});

const deleteSub = client.models.Todo.onDelete().subscribe({
  next: payload => // Process incoming messages
});

const cleanupSubscriptions = () => {
  createSub.unsubscribe();
  updateSub.unsubscribe();
  deleteSub.unsubscribe();
}
```

</Accordion>

## Unsubscribe from a subscription

You can also unsubscribe from events by using subscriptions by implementing the following:

```ts
// Stop receiving data updates from the subscription
sub.unsubscribe();
```

## Conclusion

Congratulations! You have finished the **Subscribe to real-time events** guide. In this guide, you set up subscriptions for real-time events and learned how to filter and cancel these subscriptions when needed.

### Next steps

Our recommended next steps include continuing to build out and customize your information architecture for your data. Some resources that will help with this work include:

- [Customize your auth rules](/[platform]/build-a-backend/data/customize-authz/)
- [Customize your data model](/[platform]/build-a-backend/data/data-modeling/)
- [Add custom business logic](/[platform]/build-a-backend/data/custom-business-logic/)
