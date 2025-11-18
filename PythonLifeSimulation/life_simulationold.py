import time
import os
import random
import math

# --- STEP 1: Handle Colorama Import ---
try:
    import colorama
    # --- We are NOT using init(), to send raw codes ---
    Fore = colorama.Fore
    Back = colorama.Back 
    Style = colorama.Style
    COLOR_ENABLED = True
except ImportError:
    print("Colorama library not found. Running in black and white.")
    print("To enable colors, run: py -m pip install colorama")
    class DummyStyle:
        def __getattr__(self, name):
            return ""
    Fore = DummyStyle()
    Back = DummyStyle()
    Style = DummyStyle()
    COLOR_ENABLED = False


# --- SIMULATION PARAMETERS (User's "Hardcore" settings) ---
WORLD_WIDTH = 70
WORLD_HEIGHT = 30
STARTING_AGENTS = 15
STARTING_FOOD = 20  # User setting
STARTING_WOOD = 10  # User setting

# Resources spawn every N turns
FOOD_SPAWN_RATE = 10 # User setting
WOOD_SPAWN_RATE = 100 # User setting

# Farming Parameters
FOOD_FRESHNESS = 150 # How many turns food lasts before spoiling
GROW_TIME = 30 # How many turns for a plant to grow

# --- NEW CAMPFIRE CODE ---
CAMPFIRE_BURN_TIME = 200 # How many turns a campfire lasts
CAMPFIRE_WOOD_COST = 2

# How fast the simulation runs
SIM_SPEED = 0.15  # (Slower so you can see!)

# --- GENE PARAMETERS (Min, Max, Mutation Rate) ---
GENE_RANGES = {
    'vision': (3, 10, 0.1),
    'speed': (1, 3, 0.1), # Agents can evolve a speed < 1.0
    'metabolism': (0.5, 2.0, 0.1),
    'aggression': (0.0, 0.5, 0.1),
    'builder': (0.0, 1.0, 0.1),
    'mating_drive': (100, 150, 5.0),
    'sociability': (0.0, 1.0, 0.1),
    'farming': (0.0, 1.0, 0.1) 
}

# --- HELPER FUNCTIONS ---

def clear_screen():
    """
    --- "SMOOTH" FIX ---
    Prints the raw "jump to top-left" ANSI code.
    This stops the flicker/roil from 'os.system('clear')'.
    """
    print("\033[H")

def clamp(value, min_val, max_val):
    """Clamps a value between a min and max."""
    return max(min_val, min(value, max_val))

def get_distance(x1, y1, x2, y2):
    """Calculates Euclidean distance."""
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

# --- AGENT CLASS ---

class Agent:
    def __init__(self, x, y, world, genes=None):
        self.world = world
        self.x = x
        self.y = y
        self.char = 'A'
        
        # Physical Needs
        self.energy = 100
        self.wood_carried = 0
        self.mate_cooldown = 0
        self.seeds_carried = random.randint(0, 2) # Start with a few seeds
        
        self.social = random.uniform(30.0, 80.0) 
        
        self.home_location = None 
        
        # Buffs
        self.social_buff_timer = 0 
        self.contentment_buff_timer = 0 
        
        self.state = "WANDERING" 
        
        self.exploration_vector = (0, 0) 
        
        self.skills = {
            'foraging': 0.0,
            'social': 0.0,
            'building': 0.0,
            'navigation': 0.0,
            'combat': 0.0,
            'farming': 0.0 
        }
        
        if genes:
            self.genes = genes
        else:
            self.genes = self.create_random_genes()
            
    def create_random_genes(self):
        genes = {}
        for gene, (min_val, max_val, _) in GENE_RANGES.items():
            genes[gene] = random.uniform(min_val, max_val)
        return genes

    def update(self):
        """The main "think" loop for the agent."""
        
        # 1. Update basic needs
        metabolism_cost = self.genes['metabolism']
        
        # Home buff
        if self.home_location is not None and (self.x, self.y) == self.home_location:
            metabolism_cost *= 0.5 # 50% energy save!
            
        # Social buff
        if self.social_buff_timer > 0:
            metabolism_cost *= 0.8 # 20% energy save!
            self.social_buff_timer -= 1
            
        # --- NEW CAMPFIRE CODE ---
        # Check for "Cozy" buff from a nearby campfire
        nearby_campfire = self.world.get_nearest(self.x, self.y, 2, self.world.campfires.keys())
        if nearby_campfire:
            metabolism_cost *= 0.9 # 10% energy save
            self.social += 0.5 # Passively get social
        # --- END NEW CAMPFIRE CODE ---
            
        self.energy -= metabolism_cost
        if self.mate_cooldown > 0:
            self.mate_cooldown -= 1
            
        # Update Social Need
        if self.contentment_buff_timer > 0:
            self.contentment_buff_timer -= 1
        else:
            vision_radius = int(self.genes['vision'])
            nearby_agents = self.world.get_nearest_agents(self.x, self.y, vision_radius, self)
            if not nearby_agents and not nearby_campfire: # Campfires also help social
                self.social -= self.genes['sociability'] * 0.5 
            else:
                self.social += 0.1
            self.social = clamp(self.social, 0, 100)
            
        # 2. Check for death
        if self.energy <= 0:
            self.die()
            return

        # 3. Decide what to do
        self.decide_state() 
        
        # 4. Execute the action
        self.execute_action()

    def decide_state(self):
        """This is the "brain" of the agent."""
        vision_radius = int(self.genes['vision'])
        food_in_sight = self.world.get_nearest(self.x, self.y, vision_radius, self.world.food)
        
        # Priority 0: Hopeless/Sad
        if self.energy < 20 and not food_in_sight:
            self.state = "SOCIAL_SAD" # 's'
            return
            
        # Priority 1: Survival (Energy)
        if self.energy < 70:
            self.state = "FORAGING" # 'f'
            return

        # Priority 2: Social Need
        if self.social < 30 and self.genes['sociability'] > 0.2:
            self.state = "SEEKING_SOCIAL" # 't'
            return
            
        # Priority 3: Building (COMMUNITY LOGIC)
        if self.home_location is None and self.genes['builder'] > random.random():
            wood_cost_needed = 3 - int(self.skills['building'] * 0.5)
            if wood_cost_needed < 1: wood_cost_needed = 1
            
            # Step 1: Do we have enough wood?
            if self.wood_carried < wood_cost_needed:
                self.state = "GETTING_WOOD" # 'w'
                return
            
            # Step 2: We have wood. Is our CURRENT tile a good place to build?
            community_radius = vision_radius + 5 
            nearby_homes = self.world.get_nearest(self.x, self.y, community_radius, self.world.homes)
            is_social = self.genes['sociability'] > 0.5

            if self.is_clear_tile(self.x, self.y):
                if is_social:
                    if nearby_homes or not self.world.homes:
                        self.state = "BUILDING" # 'b'
                    else:
                        self.state = "SEEKING_COMMUNITY" # 'C'
                else:
                    if not nearby_homes:
                        self.state = "BUILDING" # 'b'
                    else:
                        self.state = "SEEKING_REMOTE_SPOT" # 'R'
            else:
                if is_social:
                    if nearby_homes or not self.world.homes:
                        self.state = "WANDERING_TO_BUILD" # 'B'
                    else:
                        self.state = "SEEKING_COMMUNITY" # 'C'
                else:
                    if not nearby_homes:
                        self.state = "WANDERING_TO_BUILD" # 'B'
                    else:
                        self.state = "SEEKING_REMOTE_SPOT" # 'R'
            return
        
        # Priority 4: Farming
        if self.seeds_carried > 0 and self.energy > 80 and self.genes['farming'] > random.random():
            self.state = "PLANTING" # 'p'
            return
            
        # --- NEW CAMPFIRE CODE ---
        # Priority 5: Build Campfire (Luxury Task)
        if self.energy > 120 and self.social > 50 and \
           self.genes['builder'] > 0.5 and self.wood_carried >= CAMPFIRE_WOOD_COST:
            self.state = "BUILDING_CAMPFIRE" # 'c'
            return
        # --- END NEW CAMPFIRE CODE ---
            
        # Priority 6: Happy/Content
        if self.energy > 150 and self.social > 80:
            self.state = "SOCIAL_HAPPY" # 'S'
            return
            
        # Default State: Wandering
        self.state = "WANDERING" # 'A'

    def execute_action(self):
        """Performs the action associated with the current state."""
        vision_radius = int(self.genes['vision'])
        food = self.world.get_nearest(self.x, self.y, vision_radius, self.world.food)
        wood = self.world.get_nearest(self.x, self.y, vision_radius, self.world.wood)
        agents = self.world.get_nearest_agents(self.x, self.y, vision_radius, exclude_self=self)
        
        # Handle "Anger" (Aggression)
        agents_on_tile = [a for a in self.world.agents if a.x == self.x and a.y == self.y and a != self]
        if agents_on_tile:
            target = random.choice(agents_on_tile)
            if random.random() < self.genes['aggression']:
                self.attack(target) # 'X'
                return 
        
        # --- Execute State ---
        
        if self.state == "FORAGING":
            if (self.x, self.y) in self.world.food:
                self.eat()
            elif food:
                self.move_towards(food[0], food[1])
            else:
                self.move_exploring() 

        elif self.state == "GETTING_WOOD":
            if (self.x, self.y) in self.world.wood:
                self.take_wood()
            elif wood:
                self.move_towards(wood[0], wood[1])
            else:
                self.move_exploring()

        elif self.state == "BUILDING":
            self.build_home()

        elif self.state == "WANDERING_TO_BUILD":
            self.move_randomly(speed_factor=0.5, persistent_chance=0.0)

        elif self.state == "SEEKING_COMMUNITY":
            all_homes = self.world.get_nearest(self.x, self.y, 999, self.world.homes) 
            if all_homes:
                self.move_towards(all_homes[0], all_homes[1])
            else:
                self.move_exploring()

        elif self.state == "SEEKING_REMOTE_SPOT":
            self.move_exploring()

        elif self.state == "PLANTING":
            if self.is_clear_tile(self.x, self.y):
                self.plant_seed()
            else:
                self.move_randomly(persistent_chance=0.0)
                
        # --- NEW CAMPFIRE CODE ---
        elif self.state == "BUILDING_CAMPFIRE":
            if self.is_clear_tile(self.x, self.y):
                self.build_campfire()
            else:
                # Wiggle to find a clear spot nearby
                self.move_randomly(speed_factor=0.5, persistent_chance=0.0)
        # --- END NEW CAMPFIRE CODE ---

        elif self.state == "MATING":
            pass
                
        elif self.state == "SEEKING_SOCIAL": # 't'
            if agents:
                target_agent = agents[0] 
                if get_distance(self.x, self.y, target_agent.x, target_agent.y) < 2.0:
                    self.communicate(target_agent)
                else:
                    self.move_towards(target_agent.x, target_agent.y)
            else:
                self.move_exploring() 
                
        elif self.state == "SOCIAL_HAPPY": # 'S'
            self.move_randomly(speed_factor=0.5, persistent_chance=0.0) 

        elif self.state == "SOCIAL_SAD": # 's'
            pass 
            
        elif self.state == "WANDERING":
            self.move_exploring()
            
        elif self.state == "COMMUNICATING": # 'T'
            pass 

    def is_clear_tile(self, x, y):
        """Helper to check if a tile is empty for building/planting."""
        if (x,y) in self.world.homes: return False
        if (x,y) in self.world.food: return False
        if (x,y) in self.world.wood: return False
        if (x,y) in self.world.growing_plants: return False
        # --- NEW CAMPFIRE CODE ---
        if (x,y) in self.world.campfires: return False
        # --- END NEW CAMPFIRE CODE ---
        return True

    def move_towards(self, target_x, target_y):
        """Moves one step towards a target coordinate."""
        self.exploration_vector = (0, 0)
        
        steps = int(self.genes['speed'])
        if steps < 1:
            steps = 1
        
        for _ in range(steps):
            dx, dy = 0, 0
            if self.x < target_x: dx = 1
            elif self.x > target_x: dx = -1
            if self.y < target_y: dy = 1
            elif self.y > target_y: dy = -1
            
            self.x = clamp(self.x + dx, 0, self.world.width - 1)
            self.y = clamp(self.y + dy, 0, self.world.height - 1)
            
            self.skills['navigation'] = clamp(self.skills['navigation'] + 0.01, 0, 5.0) 
            cost_multiplier = 1.0 - (self.skills['navigation'] * 0.1) 
            if cost_multiplier < 0.5: cost_multiplier = 0.5
            
            self.energy -= (0.1 * self.genes['speed']) * cost_multiplier

    def move_randomly(self, speed_factor=1.0, persistent_chance=0.0):
        """Moves randomly (0.0 = wiggle) or persistently (0.8 = explore)."""
        steps = int(self.genes['speed'] * speed_factor)
        if steps < 1: 
            steps = 1
        
        for _ in range(steps):
            stuck = False
            if self.exploration_vector != (0, 0):
                new_x = clamp(self.x + self.exploration_vector[0], 0, self.world.width - 1)
                new_y = clamp(self.y + self.exploration_vector[1], 0, self.world.height - 1)
                if new_x == self.x and new_y == self.y:
                    stuck = True 

            if self.exploration_vector == (0, 0) or stuck or random.random() > persistent_chance:
                while True: 
                    self.exploration_vector = (random.randint(-1, 1), random.randint(-1, 1))
                    if self.exploration_vector != (0, 0):
                        break
            
            dx, dy = self.exploration_vector
            self.x = clamp(self.x + dx, 0, self.world.width - 1)
            self.y = clamp(self.y + dy, 0, self.world.height - 1)
            
            self.skills['navigation'] = clamp(self.skills['navigation'] + 0.01, 0, 5.0) 
            cost_multiplier = 1.0 - (self.skills['navigation'] * 0.1) 
            if cost_multiplier < 0.5: cost_multiplier = 0.5
            
            self.energy -= (0.1 * self.genes['speed']) * cost_multiplier

    def move_exploring(self):
        """Helper function to call move_randomly with smart settings."""
        self.move_randomly(speed_factor=1.0, persistent_chance=0.8)

    def eat(self):
        """Eats food on the current tile."""
        if (self.x, self.y) in self.world.food:
            self.world.food.remove((self.x, self.y))
            if (self.x, self.y) in self.world.food_freshness:
                del self.world.food_freshness[(self.x, self.y)]
            
            self.skills['foraging'] = clamp(self.skills['foraging'] + 0.1, 0, 10.0) 
            energy_gain = 50 + (self.skills['foraging'] * 5) 
            self.energy += energy_gain
            
            seed_chance = 0.3 + (self.skills['foraging'] * 0.05) 
            if random.random() < seed_chance:
                self.seeds_carried += 1
            
            self.state = "WANDERING"

    def take_wood(self):
        if (self.x, self.y) in self.world.wood:
            self.world.wood.remove((self.x, self.y))
            self.wood_carried += 1
            self.state = "WANDERING"
            
    def build_home(self):
        wood_cost = 3 - int(self.skills['building'] * 0.5)
        if wood_cost < 1: wood_cost = 1 
        
        if self.wood_carried >= wood_cost:
            self.wood_carried -= wood_cost
            
            if self.home_location in self.world.homes:
                self.world.homes.remove(self.home_location)
                
            self.world.homes.add((self.x, self.y))
            self.home_location = (self.x, self.y) 
            
            self.state = "WANDERING"
            self.skills['building'] = clamp(self.skills['building'] + 0.5, 0, 4.0) 
    
    # --- NEW CAMPFIRE CODE ---
    def build_campfire(self):
        if self.wood_carried >= CAMPFIRE_WOOD_COST:
            self.wood_carried -= CAMPFIRE_WOOD_COST
            self.world.campfires[(self.x, self.y)] = CAMPFIRE_BURN_TIME
            self.skills['building'] = clamp(self.skills['building'] + 0.2, 0, 4.0)
            self.state = "WANDERING"
    # --- END NEW CAMPFIRE CODE ---
            
    def attack(self, target):
        energy_cost = 10 - (self.skills['combat'] * 1.0) 
        if energy_cost < 2: energy_cost = 2 
        
        damage = 25 + (self.skills['combat'] * 5) 
        
        self.state = "ATTACKING"
        self.energy -= energy_cost
        target.energy -= damage
        self.skills['combat'] = clamp(self.skills['combat'] + 0.2, 0, 10.0) 
        
    def mate(self, partner):
        self.state = "MATING"
        partner.state = "MATING"
        
        self.energy -= 50
        partner.energy -= 50
        self.mate_cooldown = 20
        partner.mate_cooldown = 20
        
        # Gene Mixing
        new_genes = {}
        for gene in self.genes:
            avg_gene = (self.genes[gene] + partner.genes[gene]) / 2
            min_val, max_val, mut_rate = GENE_RANGES[gene]
            mutation = random.uniform(-mut_rate, mut_rate) * (max_val - min_val)
            new_genes[gene] = clamp(avg_gene + mutation, min_val, max_val)
        
        new_agent = self.world.add_agent(self.x, self.y, genes=new_genes)
        if new_agent:
            new_agent.skills = {k: 0.0 for k in self.skills}
            new_agent.home_location = None
            
        # "Contentment" buff
        self.social = 100.0 
        self.contentment_buff_timer = 25 
        partner.social = 100.0
        partner.contentment_buff_timer = 25

    def communicate(self, partner):
        self.state = "COMMUNICATING" # 'T'
        partner.state = "COMMUNICATING" 
        
        self.skills['social'] = clamp(self.skills['social'] + 0.2, 0, 10.0) 
        partner.skills['social'] = clamp(partner.skills['social'] + 0.2, 0, 10.0) 
        
        social_gain = 50 + (self.skills['social'] * 10)
        partner_social_gain = 20 + (partner.skills['social'] * 5)
        
        self.social = clamp(self.social + social_gain, 0, 100)
        partner.social = clamp(partner.social + partner_social_gain, 0, 100)
        
        # "Wellbeing" buff
        self.social_buff_timer = 20 
        partner.social_buff_timer = 20 
        
        # Mating check is now PART of socializing
        if self.energy > self.genes['mating_drive'] and self.mate_cooldown == 0 and \
           partner.energy > partner.genes['mating_drive'] and partner.mate_cooldown == 0:
            
            self.mate(partner)

    def plant_seed(self):
        """Plants a seed at the current location."""
        if self.seeds_carried > 0:
            self.seeds_carried -= 1
            self.energy -= 10 # Planting costs energy
            
            self.world.growing_plants[(self.x, self.y)] = GROW_TIME
            
            self.skills['farming'] = clamp(self.skills['farming'] + 0.2, 0, 10.0)
            self.state = "WANDERING"

    def die(self):
        """Removes the agent from the world and its home."""
        if self in self.world.agents:
            self.world.agents.remove(self)
            
        if self.home_location in self.world.homes:
            self.world.homes.remove(self.home_location)

# --- WORLD CLASS ---

class World:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.turn = 0
        
        self.agents = []
        self.food = set()
        self.wood = set()
        self.homes = set() 
        
        self.growing_plants = {} # {(x,y): turns_left}
        self.food_freshness = {} # {(x,y): turns_left}
        # --- NEW CAMPFIRE CODE ---
        self.campfires = {} # {(x,y): turns_left}
        # --- END NEW CAMPFIRE CODE ---

        # Pre-initialize stats dictionary
        self.stats = {}
        for gene in GENE_RANGES:
            self.stats['avg_{}'.format(gene)] = 0.0
        self.stats.update({
            'avg_foraging_skill': 0.0,
            'avg_social_skill': 0.0,
            'avg_building_skill': 0.0,
            'avg_navigation_skill': 0.0,
            'avg_combat_skill': 0.0,
            'avg_farming_skill': 0.0 
        })
        # --- NEW CAMPFIRE CODE ---
        self.stats.update({'population': 0, 'homes_built': 0, 'campfires_lit': 0})
        # --- END NEW CAMPFIRE CODE ---

    def add_agent(self, x=None, y=None, genes=None):
        if x is None:
            x = random.randint(0, self.width - 1)
        if y is None:
            y = random.randint(0, self.height - 1)
        
        agent = Agent(x, y, self, genes)
        self.agents.append(agent)
        return agent 

    def spawn_resources(self):
        """Spawns new food and wood on the map."""
        if self.turn % FOOD_SPAWN_RATE == 0:
            for _ in range(5): 
                if len(self.food) < (self.width * self.height * 0.1):
                    tile = self.get_random_empty_tile()
                    if tile is not None:
                        x, y = tile 
                        self.food.add((x, y))
                        self.food_freshness[(x,y)] = FOOD_FRESHNESS 

        if self.turn % WOOD_SPAWN_RATE == 0:
            for _ in range(3): 
                if len(self.wood) < (self.width * self.height * 0.05):
                    tile = self.get_random_empty_tile()
                    if tile is not None:
                        x, y = tile
                        self.wood.add((x, y))

    def update_world_objects(self):
        """Update all plants and food freshness."""
        
        # 1. Update Growing Plants
        for pos, timer in list(self.growing_plants.items()):
            timer -= 1
            if timer <= 0:
                del self.growing_plants[pos]
                if pos not in self.food and pos not in self.homes and pos not in self.wood:
                    self.food.add(pos)
                    self.food_freshness[pos] = FOOD_FRESHNESS 
            else:
                self.growing_plants[pos] = timer 
                
        # 2. Update Food Spoilage
        for pos, timer in list(self.food_freshness.items()):
            timer -= 1
            if timer <= 0:
                del self.food_freshness[pos]
                if pos in self.food:
                    self.food.remove(pos)
            else:
                self.food_freshness[pos] = timer
                
        # --- NEW CAMPFIRE CODE ---
        # 3. Update Campfires
        for pos, timer in list(self.campfires.items()):
            timer -= 1
            if timer <= 0:
                del self.campfires[pos]
            else:
                self.campfires[pos] = timer
        # --- END NEW CAMPFIRE CODE ---

    def get_random_empty_tile(self):
        """Finds a random tile that isn't occupied by anything."""
        attempts = 10
        for _ in range(attempts):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            
            occupied = any(agent.x == x and agent.y == y for agent in self.agents)
                
            if not occupied and (x,y) not in self.food and \
               (x,y) not in self.wood and (x,y) not in self.homes and \
               (x,y) not in self.growing_plants and \
               (x,y) not in self.campfires: # --- NEW CAMPFIRE CODE ---
                return x, y
        return None 

    def update(self):
        """Main update loop for the world."""
        self.turn += 1
        
        for agent in self.agents[:]:
            if agent in self.agents:
                agent.update()
            
        self.spawn_resources()
        
        self.update_world_objects()
        
        self.calculate_stats()
        
    def calculate_stats(self):
        """Calculates and updates the stats dictionary."""
        if not self.agents:
            for k in self.stats: self.stats[k] = 0
            return
            
        self.stats['population'] = len(self.agents)
        
        self.stats['homes_built'] = len([a for a in self.agents if a.home_location is not None])
        
        # --- NEW CAMPFIRE CODE ---
        self.stats['campfires_lit'] = len(self.campfires)
        # --- END NEW CAMPFIRE CODE ---
        
        # Calculate average genes
        for gene in GENE_RANGES:
            avg_key = 'avg_{}'.format(gene) 
            total = sum(agent.genes[gene] for agent in self.agents)
            self.stats[avg_key] = total / len(self.agents)
            
        # Calculate average skills
        skill_list = ['foraging', 'social', 'building', 'navigation', 'combat', 'farming']
        for skill in skill_list:
            avg_key = 'avg_{}_skill'.format(skill)
            total = sum(agent.skills[skill] for agent in self.agents)
            self.stats[avg_key] = total / len(self.agents)

    def render(self):
        """Renders the current state of the world to the console."""
        
        grid = [[(Style.DIM + Fore.WHITE + '.') for _ in range(self.width)] for _ in range(self.height)]
        
        # 1. Draw AGENTS first
        for agent in self.agents:
            is_at_home = agent.home_location is not None and (agent.x, agent.y) == agent.home_location
            if is_at_home:
                continue 
                
            color = Style.NORMAL + Fore.CYAN 
            char = '?' 
            
            if agent.social_buff_timer > 0:
                color = Style.BRIGHT + Fore.WHITE 

            if agent.state == "WANDERING":
                char = 'A'
                if agent.social_buff_timer == 0: 
                    color = Style.BRIGHT + Fore.CYAN
            elif agent.state == "FORAGING":
                char = 'f'
                if agent.social_buff_timer == 0:
                    color = Style.NORMAL + Fore.CYAN
            elif agent.state == "BUILDING":
                char = 'b'
                color = Style.BRIGHT + Fore.YELLOW
            
            elif agent.state == "WANDERING_TO_BUILD":
                char = 'B'
                color = Style.NORMAL + Fore.BLUE
            elif agent.state == "SEEKING_COMMUNITY":
                char = 'C'
                color = Style.BRIGHT + Fore.BLUE
            elif agent.state == "SEEKING_REMOTE_SPOT":
                char = 'R'
                color = Style.DIM + Fore.BLUE
                
            elif agent.state == "GETTING_WOOD":
                char = 'w' 
                color = Style.NORMAL + Fore.YELLOW
            elif agent.state == "PLANTING":
                char = 'p'
                if agent.social_buff_timer == 0:
                    color = Style.NORMAL + Fore.GREEN
                    
            # --- NEW CAMPFIRE CODE ---
            elif agent.state == "BUILDING_CAMPFIRE":
                char = 'c'
                color = Style.NORMAL + Fore.RED
            # --- END NEW CAMPFIRE CODE ---
                
            elif agent.state == "MATING":
                char = 'm'
                color = Style.BRIGHT + Fore.MAGENTA 
            elif agent.state == "ATTACKING":
                char = 'X'
                color = Style.BRIGHT + Fore.RED 
            elif agent.state == "SEEKING_SOCIAL":
                char = 't'
                if agent.social_buff_timer == 0:
                    color = Style.NORMAL + Fore.WHITE
            elif agent.state == "COMMUNICATING":
                char = 'T'
                color = Style.BRIGHT + Fore.WHITE 
            elif agent.state == "SOCIAL_HAPPY":
                char = 'S'
                color = Style.BRIGHT + Fore.MAGENTA 
            elif agent.state == "SOCIAL_SAD":
                char = 's'
                color = Style.DIM + Fore.MAGENTA 
            
            grid[agent.y][agent.x] = color + char + Style.RESET_ALL

        # 2. Draw Resources
        for (x, y) in self.food:
            grid[y][x] = Style.BRIGHT + Fore.GREEN + 'F'
        for (x, y) in self.wood:
            grid[y][x] = Style.BRIGHT + Fore.YELLOW + 'W'
        for (x, y) in self.growing_plants:
            grid[y][x] = Style.NORMAL + Fore.GREEN + 'P'
        # --- NEW CAMPFIRE CODE ---
        for (x, y) in self.campfires:
            grid[y][x] = Style.BRIGHT + Fore.RED + 'C'
        # --- END NEW CAMPFIRE CODE ---

        # 3. Draw HOMES last
        for (x, y) in self.homes:
            grid[y][x] = Style.BRIGHT + Fore.BLUE + 'H'
            
        output_buffer = []
        output_buffer.append("\033[H")
        output_buffer.append("--- A-Life Simulation --- Turn: {} ---".format(self.turn))
        for row in grid:
            output_buffer.append(" ".join(row)) 
            
        output_buffer.append(Style.BRIGHT + "\n--- LEGEND ---" + Style.RESET_ALL)
        output_buffer.append(Style.BRIGHT + Fore.WHITE + " Any" + Style.RESET_ALL + ": Agent has 20% 'Wellbeing' buff (from 'T')")
        output_buffer.append(Style.BRIGHT + Fore.CYAN + " A" + Style.RESET_ALL + ": Wandering Agent (no buff)")
        output_buffer.append(Style.NORMAL + Fore.CYAN + " f" + Style.RESET_ALL + ": Foraging (needs food)")
        output_buffer.append(Style.BRIGHT + Fore.YELLOW + " b" + Style.RESET_ALL + ": Building (placing home NOW)")
        output_buffer.append(Style.NORMAL + Fore.BLUE + " B" + Style.RESET_ALL + ": Wiggling to find build spot")
        output_buffer.append(Style.BRIGHT + Fore.BLUE + " C" + Style.RESET_ALL + ": Seeking Community (Social)")
        output_buffer.append(Style.DIM + Fore.BLUE + " R" + Style.RESET_ALL + ": Seeking Remote Spot (Loner)")
        output_buffer.append(Style.NORMAL + Fore.YELLOW + " w" + Style.RESET_ALL + ": Getting Wood (going to 'W')")
        output_buffer.append(Style.BRIGHT + Fore.MAGENTA + " m" + Style.RESET_ALL + ": Mating (flashes for 1 turn)")
        output_buffer.append(Style.BRIGHT + Fore.RED + " X" + Style.RESET_ALL + ": Attacking")
        output_buffer.append(Style.BRIGHT + Fore.MAGENTA + " S" + Style.RESET_ALL + ": Social (Happy, needs met)")
        output_buffer.append(Style.DIM + Fore.MAGENTA + " s" + Style.RESET_ALL + ": Social (Sad, hopeless)")
        output_buffer.append(Style.BRIGHT + Fore.WHITE + " T" + Style.RESET_ALL + ": Communicating (gains 'WellB')")
        output_buffer.append(Style.NORMAL + Fore.WHITE + " t" + Style.RESET_ALL + ": Learning/Seeking to Communicate")
        output_buffer.append(Style.BRIGHT + Fore.GREEN + " F" + Style.RESET_ALL + ": Food (Spoils after {} turns)".format(FOOD_FRESHNESS))
        output_buffer.append(Style.NORMAL + Fore.GREEN + " P" + Style.RESET_ALL + ": Growing Plant (Becomes 'F')")
        output_buffer.append(Style.NORMAL + Fore.GREEN + " p" + Style.RESET_ALL + ": Planting a seed")
        output_buffer.append(Style.BRIGHT + Fore.YELLOW + " W" + Style.RESET_ALL + ": Wood")
        output_buffer.append(Style.BRIGHT + Fore.BLUE + " H" + Style.RESET_ALL + ": Home (agent may be 'inside')")
        # --- NEW CAMPFIRE CODE ---
        output_buffer.append(Style.BRIGHT + Fore.RED + " C" + Style.RESET_ALL + ": Campfire (Gives 'Cozy' buff, burns out)")
        output_buffer.append(Style.NORMAL + Fore.RED + " c" + Style.RESET_ALL + ": Building a Campfire")
        # --- END NEW CAMPFIRE CODE ---
        
        output_buffer.append(Style.BRIGHT + "\n--- SIMULATION STATS ---" + Style.RESET_ALL)
        # --- NEW CAMPFIRE CODE ---
        output_buffer.append("Population: {}   Homes Built: {}   Campfires: {}".format(
            self.stats['population'], self.stats['homes_built'], self.stats['campfires_lit']))
        # --- END NEW CAMPFIRE CODE ---
        output_buffer.append(Style.BRIGHT + "--- AVERAGE GENES (This is the 'Evolution'!) ---" + Style.RESET_ALL)
        output_buffer.append(Fore.CYAN + "  Vision:     " + Style.RESET_ALL + "{:.2f} (How far they see)".format(self.stats.get('avg_vision', 0)))
        output_buffer.append(Fore.CYAN + "  Speed:      " + Style.RESET_ALL + "{:.2f} (How fast they move)".format(self.stats.get('avg_speed', 0)))
        output_buffer.append(Fore.CYAN + "  Metabolism: " + Style.RESET_ALL + "{:.2f} (Energy burn. Lower is better)".format(self.stats.get('avg_metabolism', 0)))
        output_buffer.append(Fore.RED + "  Aggression: " + Style.RESET_ALL + "{:.2f} (Chance to attack others)".format(self.stats.get('avg_aggression', 0)))
        output_buffer.append(Fore.BLUE + "  Builder:    " + Style.RESET_ALL + "{:.2f} (Tendency to build)".format(self.stats.get('avg_builder', 0)))
        output_buffer.append(Fore.MAGENTA + "  MatingDrive:" + Style.RESET_ALL + "{:.0f} (Energy needed to mate)".format(self.stats.get('avg_mating_drive', 0)))
        output_buffer.append(Fore.WHITE + "  Sociability:" + Style.RESET_ALL + "{:.2f} (Need to be social)".format(self.stats.get('avg_sociability', 0)))
        output_buffer.append(Fore.GREEN + "  Farming:    " + Style.RESET_ALL + "{:.2f} (Tendency to plant seeds)".format(self.stats.get('avg_farming', 0)))
        
        output_buffer.append(Style.BRIGHT + "--- AVERAGE SKILLS (This is the 'Learning'!) ---" + Style.RESET_ALL)
        output_buffer.append(Fore.GREEN + "  Foraging Skill: " + Style.RESET_ALL + "{:.2f} (Get more energy/seeds from food)".format(self.stats.get('avg_foraging_skill', 0)))
        output_buffer.append(Fore.WHITE + "  Social Skill:   " + Style.RESET_ALL + "{:.2f} (Get more social from chat)".format(self.stats.get('avg_social_skill', 0)))
        output_buffer.append(Fore.BLUE + "  Building Skill: " + Style.RESET_ALL + "{:.2f} (Use less wood to build)".format(self.stats.get('avg_building_skill', 0)))
        output_buffer.append(Fore.CYAN + "  Naviga. Skill:  " + Style.RESET_ALL + "{:.2f} (Use less energy to move)".format(self.stats.get('avg_navigation_skill', 0)))
        output_buffer.append(Fore.RED + "  Combat Skill:   " + Style.RESET_ALL + "{:.2f} (Deal more combat damage)".format(self.stats.get('avg_combat_skill', 0)))
        output_buffer.append(Fore.GREEN + "  Farming Skill:  " + Style.RESET_ALL + "{:.2f} (Learn from planting)".format(self.stats.get('avg_farming_skill', 0)))
        
        print("\n".join(output_buffer) + Style.RESET_ALL)


    def get_nearest(self, x, y, radius, item_set):
        """Finds the nearest item in a set within a radius."""
        nearest_item = None
        min_dist = float('inf')
        
        for (ix, iy) in item_set:
            dist = get_distance(x, y, ix, iy)
            if dist <= radius and dist < min_dist:
                min_dist = dist
                nearest_item = (ix, iy)
        return nearest_item

    def get_nearest_agents(self, x, y, radius, exclude_self=None):
        """Finds nearest agents within a radius."""
        nearby_agents = []
        for agent in self.agents:
            if agent == exclude_self:
                continue
            dist = get_distance(x, y, agent.x, agent.y)
            if dist <= radius:
                nearby_agents.append(agent)
        return nearby_agents

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    
    # 1. Initialize the World
    world = World(WORLD_WIDTH, WORLD_HEIGHT)
    
    # 2. Add starting agents and resources
    for _ in range(STARTING_AGENTS):
        world.add_agent()
    for _ in range(STARTING_FOOD):
        tile = world.get_random_empty_tile()
        if tile:
            world.food.add(tile)
            world.food_freshness[tile] = FOOD_FRESHNESS
    for _ in range(STARTING_WOOD):
        tile = world.get_random_empty_tile()
        if tile:
            world.wood.add(tile)
        
    # 3. Run the simulation loop
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear') 
        
    try:
        while True:
            world.update()
            world.render()
            time.sleep(SIM_SPEED)
            
            if world.stats['population'] == 0 and world.turn > 100:
                print("\n--- SIMULATION END: All agents have died. ---")
                break
            if world.stats['population'] > (WORLD_WIDTH * WORLD_HEIGHT * 0.5):
                print("\n--- SIMULATION END: Overpopulation! ---")
                break
                
    except KeyboardInterrupt:
        print("\n--- Simulation stopped by user. ---")
    finally:
        print(Style.RESET_ALL)