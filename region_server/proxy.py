from projectiles import Projectile
from typing import Tuple, Any, Optional
import protobuf.region_net_pb2 as region_net
from servers_communication import create_proxy_on, remove_proxy_on, publish_proxy_remove_global
from grid_utils import ProxyObject, GridField, ProxyField, Direction, ItemState


class ProxyClient(ProxyObject):
    def __init__(self, pos_x: int, pos_y: int, user_id: int, hp: int = 400) -> None:
        super().__init__(pos_x, pos_y, user_id)
        self.hp = hp


class ProxyItem(ProxyObject):
    def __init__(self, pos_x: int, pos_y: int, id: int, name: str, kind: str) -> None:
        super().__init__(pos_x, pos_y, id)
        self.name = name
        self.kind = kind


class ProxyEnemy(ProxyObject):
    def __init__(self, pos_x: int, pos_y: int, enemy_id: int, hp: int = 50) -> None:
        super().__init__(pos_x, pos_y, enemy_id)
        self.hp = hp


# class ProxyBullet(ProxyObject):
#     def __init__(self, pos_x: int, pos_y: int, projectile: Projectile) -> None:
#         super().__init__(pos_x, pos_y, projectile.id)
#         self.projectile = projectile


async def create_proxy(
    src_node_pos: Tuple[int, int],
    dst_node_pos: Tuple[int, int],
    event: region_net.ProxyEvent,
) -> None:
    from nodes import nodes
    from region_node import RegionNode

    if dst_node := nodes.get(dst_node_pos):
        await dst_node.receive_proxy_event(event)
    else:
        node_idx = str(RegionNode.node_pos_to_idx(*dst_node_pos))
        await create_proxy_on(node_idx, event.SerializeToString())


async def remove_proxy(
    src_node_pos: Tuple[int, int],
    dst_node_pos: Tuple[int, int],
    sender_id: int,
    session_id: int,
    type: str = "Client",
) -> None:
    from nodes import nodes
    from region_node import RegionNode

    if dst_node := nodes.get(dst_node_pos):
        await dst_node.receive_proxy_remove(sender_id, type)
    else:
        if type == "Client":
            event = region_net.ProxyEvent(
                client=region_net.ClientProxy(player_id=sender_id, session_id=session_id)
            )
        elif type == "Enemy":
            event = region_net.ProxyEvent(
                enemy=region_net.EnemyProxy(player_id=sender_id, session_id=0)
            )
        node_idx = str(RegionNode.node_pos_to_idx(*dst_node_pos))
        await remove_proxy_on(node_idx, event.SerializeToString())


async def broadcast_proxy_remove(
    sender_id: int, type: str = "Client", session_id: Optional[int] = None
) -> None:
    """Remove entity's proxy from every node (notify viewers). For Client type, also publish to global channel so other servers remove the proxy."""
    from nodes import nodes

    for node in nodes.values():
        await node.receive_proxy_remove(sender_id, type)
    if type == "Client" and session_id is not None:
        await publish_proxy_remove_global(sender_id, session_id)


async def broadcast_disconnect(sender_id: int, session_id: int) -> None:
    """Remove a player's proxy from every node on every server."""
    from nodes import nodes
    from servers_communication import publish_proxy_remove_global

    for node in nodes.values():
        await node.receive_proxy_remove(sender_id)
    await publish_proxy_remove_global(sender_id, session_id)
