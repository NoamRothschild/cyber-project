import pygame
pygame.init()

class Domain_Expansion:

    Domain_types={
        "DE_power":(pygame.image.load("Domains-images/domain_FireArena.png").convert_alpha(),
        ["boost_Power","boost_Health"]
        )
    }

    def __init__(self,domain_type):
        self.domainType = domain_type
        self.domain_image, self.effects_ls_player_activate, = Domain_Expansion.Domain_types[domain_type]

    def run(self):
        return
