from projectiles import Projectile
from typing import Tuple, Any
import protobuf.region_net_pb2 as region_net
from servers_communication import create_proxy_on, remove_proxy_on
from grid_utils import ProxyObject, GridField, ProxyField, Direction


class ProxyClient(ProxyObject):
    def __init__(self, pos_x: int, pos_y: int, user_id: int, hp: int = 400) -> None:
        super().__init__(pos_x, pos_y, user_id)
        self.hp = hp

class ProxyBullet(ProxyObject):
    def __init__(self, pos_x: int, pos_y: int, projectile: Projectile) -> None:
        super().__init__(pos_x, pos_y, projectile.id)
        self.projectile = projectile


async def create_proxy(src_node_pos: Tuple[int, int], dst_node_pos: Tuple[int, int], update: region_net.RegionUpdate) -> None:
    from nodes import nodes
    from region_node import RegionNode
    if dst_node := nodes.get(dst_node_pos):
        await dst_node.receive_proxy_event(update)
    else:
        node_idx = str(RegionNode.node_pos_to_idx(*dst_node_pos))
        await create_proxy_on(node_idx, update.SerializeToString())

async def remove_proxy(src_node_pos: Tuple[int, int], dst_node_pos: Tuple[int, int], sender_id: int) -> None:
    from nodes import nodes
    from region_node import RegionNode
    if dst_node := nodes.get(dst_node_pos):
        await dst_node.receive_proxy_remove(sender_id)
    else:
        update = region_net.RegionUpdate(sender_id=sender_id)
        node_idx = str(RegionNode.node_pos_to_idx(*dst_node_pos))
        await remove_proxy_on(node_idx, update.SerializeToString())

async def broadcast_disconnect(sender_id: int) -> None:
    """Remove a player's proxy from every node on every server."""
    from nodes import nodes
    from servers_communication import publish_player_disconnect
    for node in nodes.values():
        await node.receive_proxy_remove(sender_id)
    await publish_player_disconnect(sender_id)