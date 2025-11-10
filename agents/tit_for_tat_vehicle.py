from typing import Dict, List, Tuple, Optional
from agents.negotiating_vehicle import NegotiatingVehicle
from core.messages import QueueAssignmentMessage


class TitForTatVehicle(NegotiatingVehicle):
    """
    Vehicle with Tit-for-Tat negotiation strategy.
    
    Behavioral Modes:
    - 'cooperative': Always accepts assignments (always yields)
    - 'competitive': Always demands better position (always defects)
    - 'tit_for_tat': Starts cooperative, mirrors opponents' last action
    """
    
    def __init__(self, unique_id, model, start_pos=None, position=None, battery_level=100.0, strategy='tit_for_tat', **kwargs):
        # Handle both start_pos and position parameters for flexibility
        pos = start_pos if start_pos is not None else position
        if pos is None:
            raise ValueError("Either start_pos or position must be provided")
        
        super().__init__(unique_id, model, start_pos=pos, battery_level=battery_level)
        
        # Behavioral strategy
        self.strategy = strategy  # 'cooperative', 'competitive', 'tit_for_tat'
        
        # TFT memory: track opponents' last actions
        self.opponent_history: Dict[str, List[str]] = {}
        
        # Track our own actions for opponents to observe
        self.my_last_action = 'cooperate'  # Start cooperative
        
        # Negotiation round counter
        self.negotiation_round = 0
        
    def _evaluate_assignment(self, msg: QueueAssignmentMessage) -> Tuple[bool, str]:
        """
        Evaluate assignment based on behavioral strategy.
        
        Returns:
            (should_accept, reason)
        """
        self.negotiation_round += 1
        
        self.model.log_activity(
            self.unique_id,
            f"[{self.strategy.upper()}] Round {self.negotiation_round}: Received assignment - Station_{msg.station_id}, Position {msg.queue_position}",
            "info"
        )
        
        # Strategy 1: Always Cooperative
        if self.strategy == 'cooperative':
            self.my_last_action = 'cooperate'
            self.model.log_activity(
                self.unique_id,
                f"[COOPERATIVE] Always accepting - I yield to others",
                "info"
            )
            return True, "cooperative_strategy"
        
        # Strategy 2: Always Competitive
        if self.strategy == 'competitive':
            self.my_last_action = 'defect'
            if msg.queue_position > 0:
                self.model.log_activity(
                    self.unique_id,
                    f"[COMPETITIVE] Demanding better position - I never yield!",
                    "warning"
                )
                return False, "competitive_strategy (always demand priority)"
            self.model.log_activity(
                self.unique_id,
                f"[COMPETITIVE] Already at position 0 - accepting",
                "info"
            )
            return True, "competitive_strategy (already first)"
        
        # Strategy 3: Tit-for-Tat
        if self.strategy == 'tit_for_tat':
            return self._tit_for_tat_decision(msg)
        
        # Fallback to parent's evaluation
        return super()._evaluate_assignment(msg)
    
    def _tit_for_tat_decision(self, msg: QueueAssignmentMessage) -> Tuple[bool, str]:
        """
        Tit-for-Tat decision logic.
        
        Rules:
        1. Round 1: Cooperate (accept assignment)
        2. Round 2+: Mirror aggregate behavior of opponents
           - If majority cooperated → Cooperate
           - If majority defected → Defect (demand better position)
        
        Returns:
            (should_accept, reason)
        """
        # Round 1: Always cooperate
        if self.negotiation_round == 1:
            self.my_last_action = 'cooperate'
            self.model.log_activity(
                self.unique_id,
                f"[TIT-FOR-TAT] Round 1: Starting with COOPERATION - accepting position {msg.queue_position}",
                "success"
            )
            return True, "tft_initial_cooperation"
        
        # Round 2+: Check opponents' behavior
        # Analyze who is at better positions than us
        opponents_actions = []
        opponent_details = []
        
        for vid, (sid, qpos) in msg.all_assignments.items():
            if vid == self.unique_id:
                continue
            
            # Same station competition
            if sid == msg.station_id:
                # Get vehicle's history
                if vid not in self.opponent_history:
                    self.opponent_history[vid] = []
                
                if qpos < msg.queue_position:
                    # They demanded priority (defected)
                    action = 'defect'
                    opponent_details.append(f"{vid}:DEFECTED(pos={qpos})")
                else:
                    action = 'cooperate'
                    opponent_details.append(f"{vid}:COOPERATED(pos={qpos})")
                
                self.opponent_history[vid].append(action)
                opponents_actions.append(action)
        
        # Log opponent analysis
        if opponent_details:
            self.model.log_activity(
                self.unique_id,
                f"[TIT-FOR-TAT] Analyzing opponents: {', '.join(opponent_details)}",
                "info"
            )
        
        # Decision: Mirror majority behavior
        if not opponents_actions:
            self.my_last_action = 'cooperate'
            self.model.log_activity(
                self.unique_id,
                f"[TIT-FOR-TAT] No competitors at my station - COOPERATING",
                "info"
            )
            return True, "tft_no_opponents"
        
        defect_count = opponents_actions.count('defect')
        cooperate_count = opponents_actions.count('cooperate')
        
        if defect_count > cooperate_count:
            self.my_last_action = 'defect'
            self.model.log_activity(
                self.unique_id,
                f"[TIT-FOR-TAT] Majority DEFECTED ({defect_count}/{len(opponents_actions)}) - RETALIATING! Demanding better position",
                "warning"
            )
            if msg.queue_position > 0:
                return False, f"tft_retaliation (opponents defected {defect_count}/{len(opponents_actions)})"
            return True, "tft_retaliation (already first)"
        
        self.my_last_action = 'cooperate'
        self.model.log_activity(
            self.unique_id,
            f"[TIT-FOR-TAT] Majority COOPERATED ({cooperate_count}/{len(opponents_actions)}) - COOPERATING back",
            "success"
        )
        return True, f"tft_cooperation (mirroring {cooperate_count}/{len(opponents_actions)} cooperative)"
    
    def get_strategy_info(self) -> Dict[str, any]:
        """Get information about vehicle's strategy and history."""
        return {
            'strategy': self.strategy,
            'last_action': self.my_last_action,
            'negotiation_round': self.negotiation_round,
            'opponent_history': self.opponent_history,
        }
