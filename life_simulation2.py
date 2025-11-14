# -*- coding: utf-8 -*-
import time
import os
import random
import math

# --- SIMULATION LIFE STAGE CONSTANTS ---
ADULT_AGE = 100
OLD_AGE = 1500
MAX_AGE = 2000
# ---------------------------------------

# Love Parameters (MODIFIED)
STARTING_LOVE = 10 # FIX: Lowered significantly to make Love=0 achievable
LOVE_GAIN_EAT = 2.5
LOVE_GAIN_SOCIAL = 5 
LOVE_GAIN_REST = 0.5 
LOVE_LOSS_STRUGGLE = 2.5 # FIX: Increased significantly (from 1.0) to allow Love to drop to zero faster
PASSIVE_LOVE_GAIN = 0.0 # FIX: Removed passive gain to make Love=0 possible

# PAUSE THRESHOLDS (MODIFIED)
PAUSE_ENERGY_THRESHOLD = 100
PAUSE_SOCIAL_THRESHOLD = 80 # FIX: Raised from 50 to encourage agents to linger and communicate

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
# --- FINAL BALANCE FIX: Increase starting food to reduce early competition ---
STARTING_FOOD = 120  
STARTING_WOOD = 80  

# Resources spawn every N turns
FOOD_SPAWN_RATE = 25 
WOOD_SPAWN_RATE = 80 

# Farming Parameters
FOOD_FRESHNESS = 185 
GROW_TIME = 10 

# Tree Parameters
TREE_GROW_TIME = 10 
WOOD_SEED_CHANCE = 0.5
FOOD_SEED_BASE_CHANCE = 0.1 # NEW: Base chance to drop a food seed when consuming food

# Campfire Parameters
CAMPFIRE_BURN_TIME = 300 
CAMPFIRE_WOOD_COST = 3 
CAMPFIRE_REFUEL_THRESHOLD = 100 

# --- NEW: Home Durability (MODIFIED) ---
HOME_DURABILITY_START = 3
# FIX: Drastically lowered decay rate (from 1500) so homes require maintenance
HOME_DECAY_RATE = 400 
# --- END NEW ---

# How fast the simulation runs
SIM_SPEED = 0.15  

# --- GENE PARAMETERS (Min, Max, Mutation Rate) ---
GENE_RANGES = {
    'vision': (3, 10, 0.1),
    'speed': (1, 3, 0.1), 
    'metabolism': (0.5, 2.0, 0.1),
    'aggression': (0.0, 0.5, 0.1),
    'builder': (0.0, 1.0, 0.1),
    'mating_drive': (60, 130, 5.0), 
    'sociability': (0.0, 1.0, 0.1),
    'farming': (0.0, 1.0, 0.1) 
}

# --- HELPER FUNCTIONS ---

def clear_screen():
    """
    Prints the raw "jump to top-left" ANSI code.
    """
    print("\033[H")

def clamp(value, min_val, max_val):
    """Clamps a value between a min and max."""
    return max(min_val, min(value, max_val))

def get_distance(x1, y1, x2, y2):
    """
    Calculates Euclidean distance.
    """
    return math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

# --- AGENT CLASS ---

class Agent:
    def __init__(self, x, y, world, genes=None):
        self.world = world
        self.x = x
        self.y = y
        self.char = 'A'
        self.id = self.world.get_next_agent_id() 
        
        # Physical Needs
        self.energy = 150 
        self.wood_carried = 0
        self.food_carried = 0 
        self.mate_cooldown = 0
        self.seeds_carried = random.randint(0, 2) 
        self.wood_seeds_carried = random.randint(0, 1) 
        
        self.social = random.uniform(30.0, 80.0) 
        
        self.home_location = None 
        self.campfire_location = None 
        
        # Buffs
        self.social_buff_timer = 0 
        self.contentment_buff_timer = 0 
        
        self.state = "WANDERING" 
        
        self.exploration_vector = (0, 0) 
        
        # Agent Memory
        self.memory = {
            'food': set(),
            'wood': set()
        }
        
        # Struggle & Retaliation
        self.struggle_timer = 0 
        self.was_attacked_by = None 
        
        # Age Tracking and Parental Tracking
        self.age = 0 
        self.children_ids = set() 
        
        # Love System
        self.love = STARTING_LOVE
        
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
            self.genes = self.create_random_genes(stabilize=True)
            
    def create_random_genes(self, stabilize=False):
        genes = {}
        for gene, (min_val, max_val, _) in GENE_RANGES.items():
            if stabilize:
                if gene == 'metabolism':
                    genes[gene] = random.uniform(0.5, 0.8) 
                elif gene == 'speed':
                    genes[gene] = random.uniform(1.0, 3.0) 
                else:
                    genes[gene] = random.uniform(min_val, max_val)
            else:
                genes[gene] = random.uniform(min_val, max_val)
        return genes

    def update(self):
        """The main "think" loop for the agent."""
        
        # 1. Update Age and Check for Death
        self.age += 1
        
        if self.age >= MAX_AGE:
            self.die('MAX_AGE')
            return
            
        if self.age >= OLD_AGE and self.energy < 100: 
            self.die('NATURAL_DEATH_OLD')
            return
            
        # 2. Update basic needs
        metabolism_cost = self.genes['metabolism']
        
        # --- Parental Care Cost ---
        living_children_under_age = 0
        
        for child_id in list(self.children_ids):
            child = self.world.get_agent_by_id(child_id)
            if child and child.age < ADULT_AGE:
                living_children_under_age += 1
            elif child:
                self.children_ids.discard(child_id) 
            else:
                self.children_ids.discard(child_id)

        parental_cost = living_children_under_age * 0.2 
        
        if self.age < ADULT_AGE:
            metabolism_cost = parental_cost 
            if self.energy < 50:
                self.die('STARVATION_CHILD')
                return
        else:
            metabolism_cost += parental_cost
        # --- END FIX ---

        # Home buff (Family/Owner only)
        current_pos = (self.x, self.y)
        if current_pos in self.world.homes:
            home_data = self.world.homes[current_pos]
            owner_id = home_data.get('owner_id')
            
            is_owner = (self.id == owner_id)
            is_family = False
            
            if owner_id is not None:
                owner_agent = self.world.get_agent_by_id(owner_id)
                if owner_agent and self.id in owner_agent.children_ids:
                    is_family = True
            
            if is_owner or is_family:
                metabolism_cost *= 0.5 
                if self.energy < 150:
                    self.energy = clamp(self.energy + 2.0, 0, 150) # Use clamp here
                self.social = clamp(self.social + 0.5, 0, 100) 
        # --- END Home buff ---
            
        # Social buff (Campfire is communal)
        if self.social_buff_timer > 0:
            metabolism_cost *= 0.8 
            self.social_buff_timer -= 1
            
        # Check if the agent's OWNED campfire is still active
        if self.campfire_location and self.campfire_location not in self.world.campfires:
             self.campfire_location = None 
            
        # Check for "Cozy" buff from a nearby campfire
        nearby_campfire = self.world.get_nearest(self.x, self.y, 2, self.world.campfires.keys())
        if nearby_campfire:
            metabolism_cost *= 0.9 
            self.social = clamp(self.social + 0.5, 0, 100) # Passively get social
            
        self.energy -= metabolism_cost
        if self.mate_cooldown > 0:
            self.mate_cooldown -= 1
            
        # Update Social Need
        if self.contentment_buff_timer > 0:
            self.contentment_buff_timer -= 1
        else:
            vision_radius = int(self.genes['vision'])
            nearby_agents = self.world.get_nearest_agents(self.x, self.y, vision_radius, self)
            if not nearby_agents and not nearby_campfire: 
                self.social -= self.genes['sociability'] * 0.5 
            else:
                self.social += 0.1
            self.social = clamp(self.social, 0, 100)
            
        # --- NEW: Update Struggle Timer (Love Loss happens here) ---
        if self.energy < 30 or self.social < 20:
            self.struggle_timer += 1
            # Love Loss when struggling (Increased loss for combat chance)
            self.love = clamp(self.love - LOVE_LOSS_STRUGGLE, 0, STARTING_LOVE)
        else:
            self.struggle_timer = 0
            # FIX: Removed Passive Love Gain here
            # self.love = clamp(self.love + PASSIVE_LOVE_GAIN, 0, STARTING_LOVE) 
        # --- END NEW ---
            
        # --- NEW: Global Knowledge Retrieval (The Library Effect) ---
        for skill_key in self.skills:
            global_value = self.world.global_skill_knowledge.get(skill_key, 0.0)
            current_skill = self.skills[skill_key]
            if current_skill < global_value:
                self.skills[skill_key] = clamp(current_skill + 0.0001, 0, 10.0) 
        # --- END NEW ---

        # 3. Check for death
        if self.energy <= 0:
            self.die('STARVATION_ADULT')
            return

        # 4. Decide what to do
        self.decide_state() 
        
        # 5. Execute the action
        self.execute_action()

    def decide_state(self):
        """The main "think" loop for the agent."""
        vision_radius = int(self.genes['vision'])
        food_in_sight = self.world.get_nearest_in_set(self.x, self.y, vision_radius, self.world.food)
        
        conserve_energy = self.genes['metabolism'] < 0.8 and self.energy < 100
        
        # Priority -1: Retaliation
        if self.was_attacked_by is not None:
            self.state = "RETALIATING" # 'r'
            return
        
        # Priority 0: Hopeless/Sad
        if (self.energy < 20 or self.social < 10) and not food_in_sight and not self.memory['food']:
            self.state = "SOCIAL_SAD" # 's'
            return
            
        # Priority 1: Survival (Energy)
        forage_threshold = 70 
        if self.age < ADULT_AGE: 
            forage_threshold = 100 
            
        if self.energy < forage_threshold or (self.food_carried > 0 and self.energy < 150):
            self.state = "FORAGING" # 'f'
            return
            
        # Priority 1.5: Campfire Refuel
        nearby_campfire = self.world.get_nearest(self.x, self.y, vision_radius, self.world.campfires.keys())
        if nearby_campfire:
            campfire_timer = self.world.campfires.get(nearby_campfire)
            if campfire_timer and campfire_timer < CAMPFIRE_REFUEL_THRESHOLD:
                if self.wood_carried < 1:
                    self.state = "GETTING_WOOD" # 'w'
                    return
                else:
                    self.state = "REFUELING_CAMPFIRE" # 'R' 
                    return

        # Priority 2: Home Repair (MODIFIED: Repair if durability is not max)
        if self.home_location:
            home_data = self.world.homes.get(self.home_location)
            
            # Check if the home exists, durability is less than max, AND the agent is the owner
            is_owner = home_data.get('owner_id') == self.id
            # FIX: Check if durability is less than max (HOME_DURABILITY_START is 3)
            if home_data and home_data['durability'] < HOME_DURABILITY_START and is_owner: 
                if self.wood_carried < 1:
                    self.state = "GETTING_WOOD" # 'w' 
                    return
                else:
                    self.state = "REPAIRING_HOME" # 'E'
                    return

        # Priority 3: Social Need (MODIFIED: Check social more often)
        # FIX: Raised social threshold from 30 to 60
        if self.social < 60 and self.genes['sociability'] > 0.2:
            self.state = "SEEKING_SOCIAL" # 't'
            return
            
        # Priority 4: Claim or Build Home (MODIFIED: Only if agent has NO home)
        if self.home_location is None:
            # Step 1: Try to claim an empty one
            empty_home = self.world.get_empty_home()
            if empty_home:
                self.state = "CLAIMING_HOME" # 'k'
                return
            
            # Step 2: If no empty homes AND pop > homes, build one
            elif (len(self.world.homes) < len(self.world.agents)) and (self.genes['builder'] > random.random()):
                
                if conserve_energy:
                    self.state = "FORAGING" 
                    return
                
                wood_cost_needed = 3 - int(self.skills['building'] * 0.5)
                if wood_cost_needed < 1: wood_cost_needed = 1
                
                if self.wood_carried < wood_cost_needed:
                    self.state = "GETTING_WOOD" 
                    return
                
                community_radius = vision_radius + 5 
                nearby_homes = self.world.get_nearest(self.x, self.y, community_radius, self.world.homes.keys())
                is_social = self.genes['sociability'] > 0.5

                if self.is_clear_tile(self.x, self.y):
                    if is_social:
                        if nearby_homes or not self.world.homes:
                            self.state = "BUILDING" # 'b'
                        else:
                            self.state = "SEEKING_COMMUNITY" # 'C'
                    else:
                        if not nearby_homes:
                            self.state = "BUILDING" 
                        else:
                            self.state = "SEEKING_REMOTE_SPOT" # 'S'
                else:
                    if is_social:
                        if nearby_homes or not self.world.homes:
                            self.state = "WANDERING_TO_BUILD" # 'B'
                        else:
                            self.state = "SEEKING_COMMUNITY" 
                    else:
                        if not nearby_homes:
                            self.state = "WANDERING_TO_BUILD" 
                        else:
                            self.state = "SEEKING_REMOTE_SPOT" 
                return
        
        # Priority 5: Farming (Food Seeds)
        if self.seeds_carried > 0 and self.energy > 80 and self.genes['farming'] > random.random():
            if self.home_location:
                dist = get_distance(self.x, self.y, self.home_location[0], self.home_location[1])
                if dist > 5: 
                    self.state = "GOING_HOME_TO_FARM" # 'G'
                else:
                    self.state = "PLANTING" # 'p'
            else:
                self.state = "PLANTING" # 'p'
            return

        # Priority 5.5: Planting Trees (if wood is scarce)
        if self.wood_seeds_carried > 0 and self.energy > 80 and \
           (len(self.world.wood) < STARTING_WOOD) and (self.genes['builder'] > random.random()): 
            if self.home_location:
                dist = get_distance(self.x, self.y, self.home_location[0], self.home_location[1])
                if dist > 5:
                    self.state = "GOING_HOME_TO_PLANT_WOOD" 
                else:
                    self.state = "PLANTING_WOOD"
            else:
                self.state = "PLANTING_WOOD" 
            return
            
        # Priority 6: Build Campfire (MODIFIED: Only if no nearby active fire)
        # Check if there is a fire *near* the agent, not just if the agent owns one
        nearby_active_fire = self.world.get_nearest(self.x, self.y, 5, self.world.campfires.keys())

        if self.energy > 120 and self.social > 50 and \
           self.genes['builder'] > 0.5 and \
           nearby_active_fire is None: # FIX: Only build if no nearby fire
           
            if conserve_energy:
                self.state = "FORAGING" 
                return
            
            wood_cost_needed = CAMPFIRE_WOOD_COST - int(self.skills['building'] * 0.5)
            if wood_cost_needed < 1: wood_cost_needed = 1
            
            if self.wood_carried >= wood_cost_needed:
                 self.state = "BUILDING_CAMPFIRE" # 'c'
                 return
            elif self.wood_carried < wood_cost_needed:
                 self.state = "GETTING_WOOD"
                 return
            
        # Priority 7: Share Resources
        if self.energy > 100 and self.social > 50 and (self.wood_carried > 3 or self.food_carried >= 1):
            nearby_agents = self.world.get_nearest_agents(self.x, self.y, vision_radius, self)
            needy_agents = [a for a in nearby_agents if a.energy < 70 and a.food_carried < 1] 
            if needy_agents:
                self.state = "SHARING" # 'g'
                return
            
        # Default State: Wandering
        # Priority 8: Happy/Content
        self.state = "WANDERING" # 'A'

    def execute_action(self):
        """Performs the action associated with the current state."""
        vision_radius = int(self.genes['vision'])
        
        # 1. Check ALL visible resources
        food_in_sight = self.world.get_nearest_in_set(self.x, self.y, vision_radius, self.world.food)
        wood_in_sight = self.world.get_nearest_in_set(self.x, self.y, vision_radius, self.world.wood)
        agents = self.world.get_nearest_agents(self.x, self.y, vision_radius, exclude_self=self)

        # 2. Get nearest target from combined vision and memory
        best_food_target = self.get_closest_combined_target('food', food_in_sight)
        best_wood_target = self.get_closest_combined_target('wood', wood_in_sight)
        
        # --- Handle "Anger" (Aggression) ---
        agents_on_tile = [a for a in self.world.agents if a.x == self.x and a.y == self.y and a != self]
        if agents_on_tile:
            target = random.choice(agents_on_tile)
            
            # Dynamic Aggression based on struggle
            base_aggression = self.genes['aggression']
            struggle_bonus = min(self.struggle_timer * 0.0005, 0.5) 
            dynamic_aggression = base_aggression + struggle_bonus
            
            # --- COMBAT LOCK CHECK: Love is ZERO and Energy is high enough ---
            if self.love <= 0 and self.energy > 80 and random.random() < dynamic_aggression:
                self.attack(target) 
                return 
        
        # --- Execute State ---
        
        if self.state == "FORAGING":
            if self.food_carried > 0 and self.energy < 150: 
                self.consume_food() 
            elif (self.x, self.y) in self.world.food and self.food_carried < 2: 
                self.pickup_food()
            elif best_food_target: 
                self.move_towards(best_food_target[0], best_food_target[1])
                if get_distance(self.x, self.y, best_food_target[0], best_food_target[1]) < 2.0:
                    if (self.x, self.y) not in self.world.food:
                        self.memory['food'].discard(best_food_target)
            else:
                self.move_exploring() 

        elif self.state == "GETTING_WOOD":
            if self.wood_carried >= 3: 
                self.state = "WANDERING"
                return
            
            if (self.x, self.y) in self.world.wood and self.wood_carried < 3:
                self.take_wood()
            
            elif best_wood_target: 
                self.move_towards(best_wood_target[0], best_wood_target[1])
                if get_distance(self.x, self.y, best_wood_target[0], best_wood_target[1]) < 2.0:
                    if (self.x, self.y) not in self.world.wood:
                        self.memory['wood'].discard(best_wood_target)
            else:
                self.move_exploring()

        elif self.state == "BUILDING":
            self.build_home()

        elif self.state == "REPAIRING_HOME":
            if self.home_location:
                dist = get_distance(self.x, self.y, self.home_location[0], self.home_location[1])
                if dist < 2.0: # At home
                    if self.wood_carried > 0:
                        # FIX: Repair to max durability
                        self.world.homes[self.home_location]['durability'] = HOME_DURABILITY_START
                        self.wood_carried -= 1
                        self.skills['building'] = clamp(self.skills['building'] + 0.2, 0, 4.0)
                        self.state = "WANDERING"
                    else:
                        self.state = "GETTING_WOOD" 
                else:
                    self.move_towards(self.home_location[0], self.home_location[1])
            else:
                self.state = "WANDERING" 
                
        elif self.state == "REFUELING_CAMPFIRE":
            nearby_campfire = self.world.get_nearest(self.x, self.y, vision_radius, self.world.campfires.keys())
            if nearby_campfire:
                dist = get_distance(self.x, self.y, nearby_campfire[0], nearby_campfire[1])
                if dist < 2.0: # At campfire
                    if self.wood_carried > 0:
                        self.world.campfires[nearby_campfire] = CAMPFIRE_BURN_TIME
                        self.wood_carried -= 1
                        self.state = "WANDERING"
                    else:
                        self.state = "GETTING_WOOD"
                else:
                    self.move_towards(nearby_campfire[0], nearby_campfire[1])
            else:
                self.state = "WANDERING"

        elif self.state == "CLAIMING_HOME":
            empty_home = self.world.get_empty_home()
            if empty_home:
                dist = get_distance(self.x, self.y, empty_home[0], empty_home[1])
                if dist < 2.0: # Arrived at empty home
                    self.world.homes[empty_home]['owner_id'] = self.id
                    self.home_location = empty_home
                    self.state = "WANDERING"
                else:
                    self.move_towards(empty_home[0], empty_home[1])
            else:
                self.state = "WANDERING" 

        elif self.state == "WANDERING_TO_BUILD":
            self.move_randomly(speed_factor=0.5, persistent_chance=0.0)

        elif self.state == "SEEKING_COMMUNITY":
            all_homes = self.world.get_nearest(self.x, self.y, 999, self.world.homes.keys()) 
            if all_homes:
                self.move_towards(all_homes[0], all_homes[1])
            else:
                self.move_exploring()

        elif self.state == "SEEKING_REMOTE_SPOT":
            self.move_exploring()
        
        elif self.state == "GOING_HOME_TO_FARM":
            if self.home_location:
                dist = get_distance(self.x, self.y, self.home_location[0], self.home_location[1])
                if dist <= 5.0:
                    self.state = "PLANTING" 
                else:
                    self.move_towards(self.home_location[0], self.home_location[1])
            else:
                self.state = "PLANTING" 

        elif self.state == "PLANTING":
            if self.is_clear_tile(self.x, self.y):
                self.plant_seed()
            else:
                self.move_randomly(persistent_chance=0.0)

        elif self.state == "GOING_HOME_TO_PLANT_WOOD":
            if self.home_location:
                dist = get_distance(self.x, self.y, self.home_location[0], self.home_location[1])
                if dist <= 5.0:
                    self.state = "PLANTING_WOOD"
                else:
                    self.move_towards(self.home_location[0], self.home_location[1])
            else:
                self.state = "PLANTING_WOOD"

        elif self.state == "PLANTING_WOOD":
            if self.is_clear_tile(self.x, self.y):
                self.plant_tree()
            else:
                self.move_randomly(speed_factor=0.5, persistent_chance=0.0)
                
        elif self.state == "BUILDING_CAMPFIRE":
            if self.is_clear_tile(self.x, self.y):
                self.build_campfire()
            else:
                self.move_randomly(speed_factor=0.5, persistent_chance=0.0)

        elif self.state == "SHARING":
            nearby_agents = self.world.get_nearest_agents(self.x, self.y, vision_radius, self)
            needy_agents = [a for a in agents if a.energy < 70 and a.food_carried < 1] 
            
            if needy_agents:
                target = needy_agents[0]
                if get_distance(self.x, self.y, target.x, target.y) < 2.0:
                    if self.food_carried >= 1:
                        self.food_carried -= 1
                        target.food_carried += 1 
                        self.state = "WANDERING" 
                    elif self.wood_carried >= 1: 
                        self.wood_carried -= 1
                        target.wood_carried += 1
                        self.state = "WANDERING"
                    else:
                         self.state = "WANDERING" 
                else:
                    self.move_towards(target.x, target.y)
            else:
                self.state = "WANDERING" 

        elif self.state == "MATING":
            pass
        
        elif self.state == "RETALIATING":
            attacker = None
            for agent in self.world.agents: 
                if agent.id == self.was_attacked_by:
                    attacker = agent
                    break
            
            if attacker:
                dist = get_distance(self.x, self.y, attacker.x, attacker.y)
                if dist < 2.0:
                    self.attack(attacker)
                    self.was_attacked_by = None 
                else:
                    self.move_towards(attacker.x, attacker.y) 
            else:
                self.was_attacked_by = None
                self.state = "WANDERING"
        
        elif self.state == "SEEKING_SOCIAL": # 't'
            # Check for agents *or* campfires
            nearby_campfire = self.world.get_nearest(self.x, self.y, vision_radius, self.world.campfires.keys())
            
            if agents:
                target_agent = agents[0] 
                if get_distance(self.x, self.y, target_agent.x, target_agent.y) < 2.0:
                    self.communicate(target_agent)
                else:
                    self.move_towards(target_agent.x, target_agent.y)
            elif nearby_campfire:
                 self.move_towards(nearby_campfire[0], nearby_campfire[1])
            else:
                self.move_exploring() 
                
        elif self.state == "SOCIAL_HAPPY": # 'S'
            # If highly satisfied, pause movement
            if self.energy > PAUSE_ENERGY_THRESHOLD and self.social > PAUSE_SOCIAL_THRESHOLD:
                pass 
            else:
                self.move_randomly(speed_factor=0.5, persistent_chance=0.0) 

        elif self.state == "SOCIAL_SAD": # 's'
            self.love = clamp(self.love + LOVE_GAIN_REST, 0, STARTING_LOVE)
            
            if self.energy < 20 and best_food_target:
                self.move_towards(best_food_target[0], best_food_target[1])
            
            elif self.social < 10:
                nearby_campfire = self.world.get_nearest(self.x, self.y, vision_radius, self.world.campfires.keys())
                if agents:
                    self.move_towards(agents[0].x, agents[0].y)
                elif nearby_campfire:
                    self.move_towards(nearby_campfire[0], nearby_campfire[1])
                else:
                    self.move_exploring()
            else:
                 self.move_exploring() 
            
        elif self.state == "WANDERING":
            # If highly satisfied, pause movement
            if self.energy > PAUSE_ENERGY_THRESHOLD and self.social > PAUSE_SOCIAL_THRESHOLD:
                
                # FIX: New logic - Small chance to move to the Library (L) when content
                if random.random() < 0.2: # 20% chance to move towards Library/Knowledge center
                    lx, ly = self.world.library_location
                    if get_distance(self.x, self.y, lx, ly) > 5.0:
                        self.move_towards(lx, ly)
                        self.state = "SEEKING_LIBRARY" # New transient state for rendering
                        return
                
                pass # Linger/observe
            else:
                # Log resources in sight to memory
                if food_in_sight: 
                    for pos in food_in_sight:
                        self.memory['food'].add(pos)
                if wood_in_sight:
                    for pos in wood_in_sight:
                        self.memory['wood'].add(pos)
                self.move_exploring()
        
        elif self.state == "SEEKING_LIBRARY":
            lx, ly = self.world.library_location
            if get_distance(self.x, self.y, lx, ly) < 2.0:
                # Arrived at library, gaining knowledge buff
                self.skills['social'] = clamp(self.skills['social'] + 0.1, 0, 10.0)
                self.state = "WANDERING"
                
            else:
                 self.move_towards(lx, ly)
            
        elif self.state == "COMMUNICATING":
            # No movement, just talking
            pass 


    def is_clear_tile(self, x, y):
        """Helper to check if a tile is empty for building/planting."""
        if (x,y) in self.world.homes: return False
        if (x,y) in self.world.food: return False
        if (x,y) in self.world.wood: return False
        if (x,y) in self.world.growing_plants: return False
        if (x,y) in self.world.growing_trees: return False 
        if (x,y) in self.world.campfires: return False
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
            cost_multiplier = 1.0 - (self.skills['navigation'] * 0.15) 
            if cost_multiplier < 0.25: cost_multiplier = 0.25
            
            self.energy -= (0.05) * cost_multiplier 

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
            cost_multiplier = 1.0 - (self.skills['navigation'] * 0.15) 
            if cost_multiplier < 0.25: cost_multiplier = 0.25
            
            self.energy -= (0.05) * cost_multiplier

    def move_exploring(self):
        """Helper function to call move_randomly with smart settings."""
        self.move_randomly(speed_factor=1.0, persistent_chance=0.8)

    def get_closest_combined_target(self, resource_type, visible_resources):
        """
        Combines visible resources and memories to find the single closest target.
        """
        possible_targets = set()
        
        possible_targets.update(visible_resources)
        
        possible_targets.update(self.memory[resource_type])
        
        if not possible_targets:
            return None
            
        nearest_item = None
        min_dist = float('inf')
        
        for (ix, iy) in possible_targets:
            dist = get_distance(self.x, self.y, ix, iy)
            if dist < min_dist:
                min_dist = dist
                nearest_item = (ix, iy)
                
        return nearest_item

    def consume_food(self):
        """Consumes 1 unit of food carried."""
        if self.food_carried > 0:
            self.food_carried -= 1
            self.skills['foraging'] = clamp(self.skills['foraging'] + 0.1, 0, 10.0) 
            energy_gain = 120 + (self.skills['foraging'] * 20) 
            self.energy += energy_gain
            self.love = clamp(self.love + LOVE_GAIN_EAT, 0, STARTING_LOVE)

            # --- NEW: Chance to drop a food seed based on foraging skill ---
            # foraging_chance is the base chance + bonus from skill
            foraging_chance = FOOD_SEED_BASE_CHANCE + (self.skills['foraging'] * 0.05)
            if random.random() < foraging_chance:
                self.seeds_carried += 1
            # --- END NEW ---

            self.state = "WANDERING"

    def pickup_food(self):
        """Picks up food from the current tile into inventory (max 2)."""
        if (self.x, self.y) in self.world.food and self.food_carried < 2: 
            self.world.food.remove((self.x, self.y))
            if (self.x, self.y) in self.world.food_freshness:
                del self.world.food_freshness[(self.x, self.y)]
            self.food_carried += 1
            self.memory['food'].discard((self.x, self.y))
            self.state = "WANDERING"

    def take_wood(self):
        """Takes 1 wood from the world tile into inventory (max 3)."""
        if (self.x, self.y) in self.world.wood and self.wood_carried < 3: 
            self.world.wood.remove((self.x, self.y))
            self.wood_carried += 1
            
            if random.random() < WOOD_SEED_CHANCE:
                self.wood_seeds_carried += 1

            self.memory['wood'].discard((self.x, self.y))
            self.state = "WANDERING"

    def build_home(self):
        wood_cost = 3 - int(self.skills['building'] * 0.5)
        if wood_cost < 1: wood_cost = 1 
        
        if self.wood_carried >= wood_cost:
            self.wood_carried -= wood_cost
            
            self.world.homes[(self.x, self.y)] = {'owner_id': self.id, 'durability': HOME_DURABILITY_START}
            self.home_location = (self.x, self.y) 
            
            self.state = "WANDERING"
            self.skills['building'] = clamp(self.skills['building'] + 0.5, 0, 4.0) 
    
    def build_campfire(self):
        wood_cost = CAMPFIRE_WOOD_COST - int(self.skills['building'] * 0.5)
        if wood_cost < 1: wood_cost = 1 
        
        if self.wood_carried >= wood_cost:
            self.wood_carried -= wood_cost
            self.world.campfires[(self.x, self.y)] = CAMPFIRE_BURN_TIME
            self.campfire_location = (self.x, self.y) 
            self.skills['building'] = clamp(self.skills['building'] + 0.2, 0, 4.0)
            self.state = "WANDERING"
            
    def attack(self, target):
        energy_cost = 10 - (self.skills['combat'] * 1.0) 
        if energy_cost < 2: energy_cost = 2 
        
        damage = 15 + (self.skills['combat'] * 8) 
        
        self.state = "ATTACKING"
        self.energy -= energy_cost
        self.energy += 10 
        
        target.energy -= damage
        self.skills['combat'] = clamp(self.skills['combat'] + 0.2, 0, 10.0) 
        
        # FIX: Aggression is emotionally costly
        self.love = clamp(self.love - 5.0, 0, STARTING_LOVE) 
        
        target.was_attacked_by = self.id
        
    def mate(self, partner):
        self.state = "MATING"
        partner.state = "MATING"
        
        self.energy -= 10
        partner.energy -= 10
        
        # FIX: Reduced mate cooldown from 70 to 65 for slightly faster frequency
        self.mate_cooldown = 65
        partner.mate_cooldown = 65
        
        # --- FIX: Determine number of children (Avg 2.2, a 10% increase from Avg 2.0) ---
        num_children = random.randint(1, 3) 
        if random.random() < 0.2: # 20% chance to have one extra child
             num_children = clamp(num_children + 1, 1, 4) # Clamp max at 4
        # --- END FIX ---
        
        for _ in range(num_children):
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
                self.children_ids.add(new_agent.id)
                partner.children_ids.add(new_agent.id)
            
        self.social = 100.0 
        self.contentment_buff_timer = 25 
        partner.social = 100.0
        partner.contentment_buff_timer = 25

    def share_skills(self, partner):
        """Agents share knowledge when communicating."""
        skills_to_share = ['foraging', 'building', 'navigation', 'farming', 'combat']
        learning_rate = 0.1 
        
        for skill in skills_to_share:
            self_skill = self.skills[skill]
            partner_skill = partner.skills[skill]
            
            if self_skill > partner_skill:
                partner.skills[skill] = clamp(partner_skill + learning_rate, 0, 10.0)
                # High skill agent contributes to global knowledge pool
                if self_skill > 2.0: 
                    self.world.global_skill_knowledge[skill] = clamp(self.world.global_skill_knowledge.get(skill, 0.0) + 0.05, 0, 10.0)
            elif partner_skill > self_skill:
                self.skills[skill] = clamp(self_skill + learning_rate, 0, 10.0)
                # High skill agent contributes to global knowledge pool
                if partner_skill > 2.0:
                    self.world.global_skill_knowledge[skill] = clamp(self.world.global_skill_knowledge.get(skill, 0.0) + 0.05, 0, 10.0)

    def communicate(self, partner):
        self.state = "COMMUNICATING" # 'T'
        partner.state = "COMMUNICATING" 
        
        # FIX: Communication has a minor energy cost
        self.energy -= 1.0 
        partner.energy -= 1.0
        
        self.skills['social'] = clamp(self.skills['social'] + 0.2, 0, 10.0) 
        partner.skills['social'] = clamp(partner.skills['social'] + 0.2, 0, 10.0) 
        
        social_gain = 50 + (self.skills['social'] * 10)
        partner_social_gain = 20 + (partner.skills['social'] * 5)
        
        self.social = clamp(self.social + social_gain, 0, 100)
        partner.social = clamp(partner.social + partner_social_gain, 0, 100)
        
        self.social_buff_timer = 20 
        partner.social_buff_timer = 20 
        
        self.love = clamp(self.love + LOVE_GAIN_SOCIAL, 0, STARTING_LOVE)
        partner.love = clamp(partner.love + LOVE_GAIN_SOCIAL, 0, STARTING_LOVE)
        
        self.share_skills(partner)
        
        # Communal Planting Decision (Survival Communication)
        if len(self.world.food) < STARTING_FOOD and \
           self.seeds_carried >= 1 and partner.seeds_carried >= 1:
            
            total_seeds = self.seeds_carried + partner.seeds_carried
            if total_seeds >= 3:
                self.seeds_carried = 0
                partner.seeds_carried = 0
                
                lx, ly = self.world.library_location
                plant_loc = (lx, ly) 
                if not self.is_clear_tile(lx, ly):
                    plant_loc = (self.x, self.y)
                
                self.world.food.add(plant_loc)
                self.world.food_freshness[plant_loc] = FOOD_FRESHNESS
                
                self.state = "FORAGING"
                partner.state = "FORAGING"
                return 
        
        # Age check added to mating condition
        if self.age >= ADULT_AGE and self.energy > self.genes['mating_drive'] and self.mate_cooldown == 0 and \
           partner.age >= ADULT_AGE and partner.energy > partner.genes['mating_drive'] and partner.mate_cooldown == 0:
            
            self.mate(partner)

    def plant_seed(self):
        """Plants a food seed at the current location."""
        if self.seeds_carried > 0:
            self.seeds_carried -= 1
            self.energy -= 10 
            
            self.world.growing_plants[(self.x, self.y)] = GROW_TIME
            
            self.skills['farming'] = clamp(self.skills['farming'] + 0.2, 0, 10.0)
            self.state = "WANDERING"

    def plant_tree(self):
        """Plants a wood seed at the current location."""
        if self.wood_seeds_carried > 0:
            self.wood_seeds_carried -= 1
            self.energy -= 10 
            
            self.world.growing_trees[(self.x, self.y)] = TREE_GROW_TIME
            
            self.skills['farming'] = clamp(self.skills['farming'] + 0.2, 0, 10.0)
            self.state = "WANDERING"

    def die(self, reason='UNKNOWN'):
        """Removes the agent from the world and makes their home 'unclaimed'."""
        
        self.world.death_causes[reason] = self.world.death_causes.get(reason, 0) + 1
        
        death_location = (self.x, self.y)
        
        # Drop wood
        for _ in range(self.wood_carried):
            self.world.wood.add(death_location)
            
        # Drop food
        for _ in range(self.food_carried):
            self.world.food.add(death_location)
            self.world.food_freshness[death_location] = FOOD_FRESHNESS 
        
        dying_agent_id = self.id
        for agent in self.world.agents[:]:
            if dying_agent_id in agent.children_ids:
                agent.children_ids.discard(dying_agent_id)
        
        if self in self.world.agents:
            self.world.agents.remove(self)
            
        if self.home_location and self.home_location in self.world.homes:
            self.world.homes[self.home_location]['owner_id'] = None

# --- WORLD CLASS ---

class World:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.turn = 0
        self.next_agent_id = 0 
        
        self.agents = []
        self.food = set()
        self.wood = set()
        
        self.generation_count = 0
        
        self.death_causes = {
            'MAX_AGE': 0, 
            'STARVATION_ADULT': 0, 
            'STARVATION_CHILD': 0, 
            'COMBAT': 0, 
            'NATURAL_DEATH_OLD': 0, 
            'UNKNOWN': 0
        }
        
        self.homes = {} 
        
        self.growing_plants = {} 
        self.growing_trees = {} 
        self.food_freshness = {} 
        self.campfires = {} 

        # Global Knowledge Pool (for the 'Library' effect)
        self.global_skill_knowledge = {
            'foraging': 0.0,
            'social': 0.0,
            'building': 5.0, 
            'navigation': 0.0,
            'combat': 0.0,
            'farming': 0.0 
        }
        # Library Location
        self.library_location = (self.width // 2, self.height // 2)

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
        self.stats.update({'population': 0, 'homes_built': 0, 'active_campfires': 0})

    def get_next_agent_id(self):
        """Returns a unique ID for a new agent."""
        self.next_agent_id += 1
        return self.next_agent_id

    def get_agent_by_id(self, agent_id):
        """Finds an agent instance by its unique ID."""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None

    def get_empty_home(self):
        """Finds the first available unclaimed home."""
        for pos, data in self.homes.items():
            if data['owner_id'] is None:
                return pos
        return None

    def add_agent(self, x=None, y=None, genes=None):
        if x is None:
            x = random.randint(0, self.width - 1)
        if y is None:
            y = random.randint(0, self.height - 1)
        
        agent = Agent(x, y, self, genes)
        
        if genes is None and len(self.agents) < STARTING_AGENTS:
            agent.genes = agent.create_random_genes(stabilize=True)
            
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
        """Update all plants, food freshness, and home durability."""
        
        # 1. Update Growing Plants (Food)
        for pos, timer in list(self.growing_plants.items()):
            timer -= 1
            if timer <= 0:
                del self.growing_plants[pos]
                if pos not in self.food and pos not in self.homes and pos not in self.wood:
                    self.food.add(pos)
                    self.food_freshness[pos] = FOOD_FRESHNESS 
            else:
                self.growing_plants[pos] = timer 
                
        # 1.5. Update Growing Trees (Wood)
        for pos, timer in list(self.growing_trees.items()):
            timer -= 1
            if timer <= 0:
                del self.growing_trees[pos]
                if pos not in self.food and pos not in self.homes and pos not in self.wood:
                    self.wood.add(pos) 
            else:
                self.growing_trees[pos] = timer 
                
        # 2. Update Food Spoilage
        for pos, timer in list(self.food_freshness.items()):
            timer -= 1
            if timer <= 0:
                del self.food_freshness[pos]
                if pos in self.food:
                    self.food.remove(pos)
            else:
                self.food_freshness[pos] = timer
                
        # 3. Update Campfires
        for pos, timer in list(self.campfires.items()):
            timer -= 1
            if timer <= 0:
                del self.campfires[pos]
            else:
                self.campfires[pos] = timer
                
        # 4. Update Home Decay (MODIFIED TO DECAY FASTER)
        if self.turn % HOME_DECAY_RATE == 0:
            for pos, data in list(self.homes.items()):
                data['durability'] -= 1
                if data['durability'] <= 0:
                    del self.homes[pos]
                    
                    for _ in range(3):
                        self.wood.add(pos)
                        
                    if data['owner_id'] is not None:
                        for agent in self.agents:
                            if agent.id == data['owner_id']:
                                agent.home_location = None
                                break

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
               (x,y) not in self.growing_trees and \
               (x,y) not in self.campfires:
                return x, y
        return None 

    def update(self):
        """Main update loop for the world."""
        self.turn += 1
        
        if self.turn % MAX_AGE == 0:
            self.generation_count += 1
        
        for agent in self.agents[:]:
            if agent in self.agents:
                agent.update()
            
        self.spawn_resources()
        
        self.update_world_objects()
        
        self.calculate_stats()
        
    def calculate_stats(self):
        """Calculates and updates the stats dictionary."""
        adult_agents = [agent for agent in self.agents if agent.age >= ADULT_AGE]
        
        if not adult_agents:
            agents_for_stats = self.agents
        else:
            agents_for_stats = adult_agents
            
        if not agents_for_stats:
            for k in self.stats: self.stats[k] = 0
            return
            
        num_agents = len(agents_for_stats)
            
        self.stats['population'] = len(self.agents) 
        self.stats['homes_built'] = len(self.homes) 
        self.stats['active_campfires'] = len(self.campfires)
        
        # Calculate average genes
        for gene in GENE_RANGES:
            avg_key = 'avg_{}'.format(gene) 
            total = sum(agent.genes[gene] for agent in agents_for_stats)
            self.stats[avg_key] = total / num_agents
            
        # Calculate average skills
        skill_list = ['foraging', 'social', 'building', 'navigation', 'combat', 'farming']
        for skill in skill_list:
            avg_key = 'avg_{}_skill'.format(skill)
            total = sum(agent.skills[skill] for agent in agents_for_stats)
            self.stats[avg_key] = total / num_agents
            
        # Calculate total deaths for percentage breakdown
        self.death_causes['TOTAL_DEATHS'] = sum(self.death_causes.values())
        if 'UNKNOWN' in self.death_causes:
            del self.death_causes['UNKNOWN']

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
                char = 'S'
                color = Style.DIM + Fore.BLUE
                
            elif agent.state == "GETTING_WOOD":
                char = 'w' 
                color = Style.NORMAL + Fore.YELLOW
            
            elif agent.state == "PLANTING" or agent.state == "PLANTING_WOOD":
                char = 'p'
                if agent.social_buff_timer == 0:
                    color = Style.NORMAL + Fore.GREEN
            elif agent.state == "GOING_HOME_TO_FARM" or agent.state == "GOING_HOME_TO_PLANT_WOOD":
                char = 'G'
                color = Style.BRIGHT + Fore.GREEN
            elif agent.state == "SHARING":
                char = 'g'
                color = Style.BRIGHT + Fore.WHITE
                    
            elif agent.state == "BUILDING_CAMPFIRE":
                char = 'c'
                color = Style.NORMAL + Fore.RED
            
            elif agent.state == "REPAIRING_HOME":
                char = 'E' 
                color = Style.BRIGHT + Fore.YELLOW
            elif agent.state == "CLAIMING_HOME":
                char = 'k' 
                color = Style.BRIGHT + Fore.BLUE
            
            elif agent.state == "REFUELING_CAMPFIRE":
                char = 'R' 
                color = Style.BRIGHT + Fore.RED
            
            elif agent.state == "MATING":
                char = 'm'
                color = Style.BRIGHT + Fore.MAGENTA 
            elif agent.state == "ATTACKING":
                char = 'X'
                color = Style.BRIGHT + Fore.RED 
            
            elif agent.state == "RETALIATING":
                char = 'r'
                color = Style.BRIGHT + Fore.RED
            
            elif agent.state == "SEEKING_SOCIAL":
                char = 't'
                if agent.social_buff_timer == 0:
                    color = Style.NORMAL + Fore.WHITE
            elif agent.state == "COMMUNICATING":
                char = 'T'
                color = Style.BRIGHT + Fore.WHITE 
            
            elif agent.state == "SOCIAL_HAPPY" or agent.state == "SEEKING_LIBRARY":
                char = 'L' # Use 'L' to show an agent is moving toward/at the library
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
        for (x, y) in self.growing_trees:
            grid[y][x] = Style.DIM + Fore.YELLOW + 'T'
        for (x, y) in self.campfires:
            grid[y][x] = Style.BRIGHT + Fore.RED + 'C'

        # 3. Draw HOMES last
        for (x, y), data in self.homes.items():
            if data['durability'] < 2:
                grid[y][x] = Style.NORMAL + Fore.BLUE + 'h' # Damaged home
            else:
                grid[y][x] = Style.BRIGHT + Fore.BLUE + 'H' # Healthy home
            
        # 4. Draw the LIBRARY 
        lx, ly = self.library_location
        grid[ly][lx] = Style.BRIGHT + Fore.MAGENTA + 'L'
        
        output_buffer = []
        
        output_buffer.append("\033[H") 
        
        output_buffer.append("--- A-Life Simulation --- Turn: {} --- Generation: {} ---".format(self.turn, self.generation_count))
        for row in grid:
            output_buffer.append(" ".join(row)) 
            
        output_buffer.append(Style.BRIGHT + "\n--- LEGEND ---" + Style.RESET_ALL)
        output_buffer.append(Style.BRIGHT + Fore.WHITE + " Any" + Style.RESET_ALL + ": 'Wellbeing' Buff")
        
        # Agent States
        output_buffer.append(
            (Style.BRIGHT + Fore.CYAN + " A" + Style.RESET_ALL + ": Wander") + " | " +
            (Style.NORMAL + Fore.CYAN + " f" + Style.RESET_ALL + ": Forage") + " | " +
            (Style.BRIGHT + Fore.MAGENTA + " L" + Style.RESET_ALL + ": Library/Happy") + " | " +
            (Style.DIM + Fore.MAGENTA + " s" + Style.RESET_ALL + ": Sad/Crisis")
        )
        output_buffer.append(
            (Style.NORMAL + Fore.WHITE + " t" + Style.RESET_ALL + ": Seek Social") + " | " +
            (Style.BRIGHT + Fore.WHITE + " T" + Style.RESET_ALL + ": Communicate") + " | " +
            (Style.BRIGHT + Fore.WHITE + " g" + Style.RESET_ALL + ": Share Wood/Food")
        )
        output_buffer.append(
            (Style.BRIGHT + Fore.RED + " X" + Style.RESET_ALL + ": Attack") + " | " +
            (Style.BRIGHT + Fore.RED + " r" + Style.RESET_ALL + ": Retaliate") + " | " + 
            (Style.BRIGHT + Fore.MAGENTA + " m" + Style.RESET_ALL + ": Mate")
        )
        output_buffer.append(
            (Style.NORMAL + Fore.YELLOW + " w" + Style.RESET_ALL + ": Get Wood") + " | " +
            (Style.BRIGHT + Fore.YELLOW + " b" + Style.RESET_ALL + ": Build Home") + " | " +
            (Style.BRIGHT + Fore.YELLOW + " E" + Style.RESET_ALL + ": Repair Home")
        )
        output_buffer.append(
            (Style.NORMAL + Fore.BLUE + " B" + Style.RESET_ALL + ": Seek Spot") + " | " +
            (Style.BRIGHT + Fore.BLUE + " C" + Style.RESET_ALL + ": Seek Comm.") + " | " +
            (Style.BRIGHT + Fore.BLUE + " k" + Style.RESET_ALL + ": Claim Home")
        )
        output_buffer.append(
            (Style.NORMAL + Fore.RED + " c" + Style.RESET_ALL + ": Build Fire") + " | " +
            (Style.BRIGHT + Fore.RED + " R" + Style.RESET_ALL + ": Refuel Fire") 
        )

        # Farming States
        output_buffer.append(
            (Style.NORMAL + Fore.GREEN + " p" + Style.RESET_ALL + ": Plant Food/Tree") + " | " + 
            (Style.BRIGHT + Fore.GREEN + " G" + Style.RESET_ALL + ": Go Home to Plant")
        )
        
        # World Objects
        output_buffer.append(
            (Style.BRIGHT + Fore.GREEN + " F" + Style.RESET_ALL + ": Food") + " | " +
            (Style.NORMAL + Fore.GREEN + " P" + Style.RESET_ALL + ": Plant") + " | " +
            (Style.DIM + Fore.YELLOW + " T" + Style.RESET_ALL + ": Tree") + " | " +
            (Style.BRIGHT + Fore.YELLOW + " W" + Style.RESET_ALL + ": Wood")
        )
        output_buffer.append(
            (Style.BRIGHT + Fore.BLUE + " H" + Style.RESET_ALL + ": Home") + " | " +
            (Style.NORMAL + Fore.BLUE + " h" + Style.RESET_ALL + ": Damaged Home") + " | " +
            (Style.BRIGHT + Fore.RED + " C" + Style.RESET_ALL + ": Campfire") + " | " +
            (Style.BRIGHT + Fore.MAGENTA + " L" + Style.RESET_ALL + ": Library")
        )
        
        output_buffer.append(Style.BRIGHT + "\n--- SIMULATION STATS ---" + Style.RESET_ALL)

        pop_str = "Population: {:<3}".format(self.stats.get('population', 0))
        home_str = "Homes Built: {:<3}".format(self.stats.get('homes_built', 0))
        fire_str = "Active Campfires: {:<3}".format(self.stats.get('active_campfires', 0))
        output_buffer.append("{}   |   {}   |   {}".format(pop_str, home_str, fire_str))
        
        output_buffer.append(Style.BRIGHT + "--- AVERAGE GENES (This is the 'Evolution'!) ---" + Style.RESET_ALL)
        output_buffer.append(Fore.CYAN + "  Vision:     " + Style.RESET_ALL + "{:>5.2f} (How far they see)".format(self.stats.get('avg_vision', 0)))
        output_buffer.append(Fore.CYAN + "  Speed:      " + Style.RESET_ALL + "{:>5.2f} (How fast they move)".format(self.stats.get('avg_speed', 0)))
        output_buffer.append(Fore.CYAN + "  Metabolism: " + Style.RESET_ALL + "{:>5.2f} (Energy burn. Lower is better)".format(self.stats.get('avg_metabolism', 0)))
        output_buffer.append(Fore.RED + "  Aggression: " + Style.RESET_ALL + "{:>5.2f} (Chance to attack others)".format(self.stats.get('avg_aggression', 0)))
        output_buffer.append(Fore.BLUE + "  Builder:    " + Style.RESET_ALL + "{:>5.2f} (Tendency to build)".format(self.stats.get('avg_builder', 0)))
        output_buffer.append(Fore.MAGENTA + "  MatingDrive:" + Style.RESET_ALL + "{:>5.0f} (Energy needed to mate)".format(self.stats.get('avg_mating_drive', 0)))
        output_buffer.append(Fore.WHITE + "  Sociability:" + Style.RESET_ALL + "{:>5.2f} (Need to be social)".format(self.stats.get('avg_sociability', 0)))
        output_buffer.append(Fore.GREEN + "  Farming:    " + Style.RESET_ALL + "{:>5.2f} (Tendency to plant seeds)".format(self.stats.get('avg_farming', 0)))
        
        output_buffer.append(Style.BRIGHT + "--- AVERAGE SKILLS (This is 'Learning'!) ---" + Style.RESET_ALL)
        output_buffer.append(Fore.GREEN + "  Foraging Skill: " + Style.RESET_ALL + "{:>5.2f} (Get more energy/seeds from food)".format(self.stats.get('avg_foraging_skill', 0)))
        output_buffer.append(Fore.WHITE + "  Social Skill:   " + Style.RESET_ALL + "{:>5.2f} (Get more social from chat)".format(self.stats.get('avg_social_skill', 0)))
        output_buffer.append(Fore.BLUE + "  Building Skill: " + Style.RESET_ALL + "{:>5.2f} (Use less wood to build)".format(self.stats.get('avg_building_skill', 0)))
        output_buffer.append(Fore.CYAN + "  Naviga. Skill:  " + Style.RESET_ALL + "{:>5.2f} (Use less energy to move)".format(self.stats.get('avg_navigation_skill', 0)))
        output_buffer.append(Fore.RED + "  Combat Skill:   " + Style.RESET_ALL + "{:>5.2f} (Deal more combat damage)".format(self.stats.get('avg_combat_skill', 0)))
        output_buffer.append(Fore.GREEN + "  Farming Skill:  " + Style.RESET_ALL + "{:>5.2f} (Learn from planting)".format(self.stats.get('avg_farming_skill', 0)))

        output_buffer.append(Style.BRIGHT + "\n--- GLOBAL KNOWLEDGE LIBRARY (Communal Learning) ---" + Style.RESET_ALL)
        
        knowledge = self.global_skill_knowledge
        output_buffer.append(Fore.GREEN + "  Foraging: " + Style.RESET_ALL + "{:>5.2f}".format(knowledge.get('foraging', 0.0)) + " | " +
                             Fore.BLUE + "Building: " + Style.RESET_ALL + "{:>5.2f}".format(knowledge.get('building', 0.0)) + " | " +
                             Fore.CYAN + "Naviga: " + Style.RESET_ALL + "{:>5.2f}".format(knowledge.get('navigation', 0.0)))
        output_buffer.append(Fore.WHITE + "  Social:   " + Style.RESET_ALL + "{:>5.2f}".format(knowledge.get('social', 0.0)) + " | " +
                             Fore.RED + "Combat:   " + Style.RESET_ALL + "{:>5.2f}".format(knowledge.get('combat', 0.0)) + " | " +
                             Fore.GREEN + "Farming:  " + Style.RESET_ALL + "{:>5.2f}".format(knowledge.get('farming', 0.0)))

        output_buffer.append(Style.BRIGHT + "\n--- DEATH ANALYSIS ---" + Style.RESET_ALL)
        total_deaths = self.death_causes.get('TOTAL_DEATHS', 0)
        
        if total_deaths > 0:
            for reason, count in self.death_causes.items():
                if reason != 'TOTAL_DEATHS' and count > 0:
                    percent = (float(count) / total_deaths) * 100 
                    output_buffer.append("  {:<20}: {} ({:>5.1f}%)".format(reason, count, percent))
        else:
            output_buffer.append("  No deaths recorded yet.")

        print("\n".join(output_buffer) + Style.RESET_ALL)


    def get_nearest(self, x, y, radius, item_set):
        """Finds the nearest item in a set within a radius."""
        nearest_item = None
        min_dist = float('inf')
        
        items = item_set
        if isinstance(item_set, dict):
            items = item_set.keys()
            
        for (ix, iy) in items:
            dist = get_distance(x, y, ix, iy)
            if dist <= radius and dist < min_dist:
                min_dist = dist
                nearest_item = (ix, iy)
        return nearest_item

    def get_nearest_in_set(self, x, y, radius, item_set):
        """Finds all items in a set within a radius and returns a list of coordinates."""
        found_items = []
        items = item_set
        if isinstance(item_set, dict):
            items = item_set.keys()
            
        for (ix, iy) in items:
            dist = get_distance(x, y, ix, iy)
            if dist <= radius:
                found_items.append((ix, iy))
        return found_items

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
                print("\n--- SIMULATION END: All agents have died. ---\n")
                break
            if world.stats['population'] > (WORLD_WIDTH * WORLD_HEIGHT * 0.5):
                print("\n--- SIMULATION END: Overpopulation! ---\n")
                break
                
    except KeyboardInterrupt:
        print("\n--- Simulation stopped by user. ---\n")
    finally:
        print(Style.RESET_ALL)