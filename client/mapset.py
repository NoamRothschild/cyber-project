WIDTH = 1500
HEIGHT =750# size of the screen

# View zoom-out: world area visible in the same window (player centered)
# VIEW_SCALE_X = 7.85 / 2.5  # visible width = WIDTH * VIEW_SCALE_X
# VIEW_SCALE_Y = 7.0 / 2.5   # visible height = HEIGHT * VIEW_SCALE_Y
VIEW_SCALE_X = 3  # visible width = WIDTH * VIEW_SCALE_X
VIEW_SCALE_Y = 3   # visible height = HEIGHT * VIEW_SCALE_Y
VIEW_WIDTH = WIDTH * VIEW_SCALE_X
VIEW_HEIGHT = HEIGHT * VIEW_SCALE_Y
# Scale from world coords to screen coords (multiply world offset by these)
SCREEN_SCALE_X = 1.0 / VIEW_SCALE_X
SCREEN_SCALE_Y = 1.0 / VIEW_SCALE_Y

FPS = 60#frame per second
SIZE=200#size of each tile
PINK=(234,54,128)#color mostly for background
FONT="Arial"

# Region node configuration (mirrors server-side region_node.py)
NODE_WIDTH = 4600   # [px]
NODE_HEIGHT = 2200  # [px]
VERTICAL_NODE_COUNT = 20
HORIZONAL_NODE_COUNT = 17
