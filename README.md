# A POC Distributed MMO Game

created for our 11th year submission project.

demo video can be found here: [drive.google.com/file/d/19a..](https://drive.google.com/file/d/19aagUMVI0Jh59KSMxzaeLqQWFu5hSSn6/view)

_video highlights_:

<table style="width: 100%;">
  <tr>
    <td width="50%"><img src="https://github.com/user-attachments/assets/08583b5a-e985-4ab9-9f3b-551a3d935bf3" alt="players" style="width: 100%;">some players vibing</td>
    <td width="50%"><img src="https://github.com/user-attachments/assets/582c192d-6f04-4370-a844-f1e2fb0c0f6f" alt="potion_use" style="width: 100%;">using a potion</td>
  </tr>
  <tr>
    <td width="50%"><img src="https://github.com/user-attachments/assets/597049d9-3077-4d7c-a20f-16eee3aabb22" alt="shop" style="width: 100%;">our beautiful shop</td>
    <td width="50%"><img src="https://github.com/user-attachments/assets/047f5bbd-fe0c-49ec-9534-0c6aebce74bc" alt="chat" style="width: 100%;">a chat system</td>
  </tr>
</table>

## Table of Contents
* [What is this about?](#what-is-this-about)
* [Running the servers](#running-the-servers)
* [Distribution of backend architecture](#distribution-of-backend-architecture)
* [Distribution of Nodes on the map](#distribution-of-nodes-on-the-map)
    * [Propagation](#propagation)
    * [Abstract Architecture of a Single Node](#abstract-architecture-of-a-single-node)
* [Handling of Network Packets](#handling-of-network-packets)
    * [Rate Limiting](#rate-limiting)
* [Incredibly good sources for writing region servers](#incredibly-good-sources-used-when-writing-the-region-server)

## What is this about?

We needed to write a MMO (Massively Multiplayer Online) game. We also had 5 school pcs to our name and were advised to make it a _distributed server architecture_.
We focused mainly about optimizations and security, while making sure to end up with a cool game with features.

---

## Running the servers

Docker must be installed. All pcs should share a LAN. If on windows, make sure developer mode is active in the windows settings (one script create sym links).

If you are on linux, you would have to read run.ps1 and copy only what you need, since utilities for non-windows machines have not been created.

First decide if using 1 or 5 region servers. 5 region servers require 5 physical computers. edit `setup_redis.py` and change `REGION_SERVERS = ` to whatever you need. one region server -> `REGION_SERVERS_LOCAL`, 5 region servers -> `REGION_SERVERS_PROD_OPTIMIZED_LAYOUT`.

Then, on each pc run:
```powershell
.\run.ps1 init
```
make sure to distribute the needed PEM files generated (list seen in stdout) to whichever pc that runs that server.

If you intend on running clients from a few pcs, you will have to copy those PEM files in the client to every pcs client folder, or make an exe using pygame that contains them all.

Next run `.\run.ps1` and look in help for how to run each server.

If running 1 region server, the id given should be 0. if running 5, ids should be 0..4 (inclusive).

Then, once they all are up and running, modify the client's config.jsonc. `SERVER_LAYOUT` should be either `single-server` or `multi-server` acordingly.

Common bug: if you get `DECRYPT ERROR` in the client's GUI after trying to log in / register, you screwd something up with the certificates. The client and server have mismatching certificates.

## Distribution of backend architecture:

<img width="1297" height="658" alt="image" src="https://github.com/user-attachments/assets/8e58d9fe-e06c-4195-9f30-e637f802ea0b" />

At the center sits Redis. All servers connect to it. It is used to cache active players data to avoid costly lookups to the sql db, used for storing session tokens which verify the users authenticity, for storing useful server metadata and more...

Clients dont have access to redis. After getting a token from the auth server, they use it to establish a connection with the chat server, and with all region servers.

---

## Distribution of Nodes on the map

_TL;DR: The whole box is the massive map. The color of each of the nodes corresponds to a uniuqe region server. This is done to balance load between multiple servers_

<img width="1666" height="1014" alt="image" src="https://github.com/user-attachments/assets/958b5b3b-d4e2-4c93-803e-8b99ac390546" />

<br>
Our map is separated into many small chunks called "nodes" (the little numbered cubes in the picture). An object may only exist in one node, but proxies of it can exist in many adjacent nodes, as long as they might be seen from there.

### Propagation:

Each action happening on the map, a player movement, a bullet shoot, an enemy attacking, an item drop, might get propagated. propagation can be local (on the same region server), which is straight forward to implement, or global, meaning it would have to get serialized and sent to another server. This sending happens via Redis Pub/Sub.

### Abstract Architecture of a Single Node

```zig
// Note: actual implementation is in python, but zig rewrite might come soon!
pub const RegionNode = struct {
  pos: [2]u32, // position of the node in the map for internal calcs
  grid: [NodeCellCount]GridSet, // a spatial hashed array mapping portions of the node into their events
  proxies: [8]ProxySet, // proxies of all nodes sorrounding us.
  clients: HashMap(u32, Client), // user_id -> Client obj
  enemy_handler: EnemyHandler,
  projectile_handler: ProjectileHandler
};

const GridField = struct {
  seen: Set(u32), // list of player session ids that saw this event. We dont sent the same event to a player twice to save up on bandwith.
  object: union(enum) { ... }, // stores the object itself along with its metadata. can be a projectile, player, item, ...
};
```

To optimize even more on preformance, we added [spatial hashing](https://matthias-research.github.io/pages/tenMinutePhysics/11-hashing.pdf) to our nodes, inspired by the architecture of Albion Online. This helps cut down uneccesary packet sends, projectile hits for objects far away and more.

Additionally, we incorporated a `seen` mechanism. We knew the internet in school is slow, so bandwith would be a bottleneck. After notifying a player about some event that occured on map, this players id is added to the seen list.

## Handling of Network Packets

Our project has a well defined protocol for communicating with servers, or between servers, available inside `protobuf/`.

Between our client and the region servers, we have two sockets. One tcp and one udp. udp with custom seq system used mostly for movement. All streams are encrypted. We adhere the "server is authority" model, meaning we don't trust anything the client sends and we verify it all on our server as well.

Example packet:
```
RegionUpdate {
  payload: BulletShot {
    gun_type: "AK-47",
    angle: 37,
    count: 1,
  }
  seq_num: 30
}

ServerResponse { ... }
```

### Rate Limiting

To avoid DOS attacks, we created a simple rate limiting mechanism. If the server said too many packets come from some ip, it blocks that ip for a set amount of time, ignoring incoming packets of it.

## Incredibly good sources used when writing the Region Server:

| Name | Description | Link |
| :--- | :--- | :--- |
| **So, you want to build an MMORPG Server** | An amazing introduction to distributed MMO systems by wirepair. | [Article](https://wirepair.org/2023/06/29/so-you-want-to-build-an-mmorpg-server) |
| **Software Architecture of an MMO** | Albion Online's talk at Quo Vadis regarding their specific game architecture. | [SlideShare](https://www.slideshare.net/slideshow/albion-online-software-architecture-of-an-mmo-talk-at-quo-vadis-2016-berlin/62724504) |
| **A Distributed Architecture for Interactive Multiplayer Games** | Research paper proposing a scalable architecture for MMOs by Ashwin R. Bharambe et al. | [Research Paper](https://www.cs.cmu.edu/~ashu/papers/cmu-cs-05-112.pdf) |
