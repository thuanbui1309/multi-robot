"""
Tit-for-Tat orchestrator for Scenario 6.

This orchestrator manages negotiation for vehicles with different behavioral strategies.
It tracks strategy outcomes and logs behavioral interactions.
"""

from typing import Dict, List
from agents.negotiating_orchestrator import NegotiatingOrchestrator
from core.messages import Message


class TitForTatOrchestrator(NegotiatingOrchestrator):
    """
    Orchestrator specialized for Tit-for-Tat scenario.
    
    Adds tracking and logging for behavioral strategies:
    - Records cooperation/defection patterns
    - Logs strategy interactions
    - Reports on negotiation outcomes
    """
    
    def __init__(self, unique_id, model, battery_threshold=30.0):
        super().__init__(unique_id, model, battery_threshold)
        
        # Track behavioral patterns
        self.cooperation_counts: Dict[str, int] = {}
        self.defection_counts: Dict[str, int] = {}
        self.strategy_outcomes: List[Dict] = []
        
    def _handle_acceptance(self, msg):
        """Override to track cooperation."""
        super()._handle_acceptance(msg)
        
        vehicle_id = msg.sender_id
        if vehicle_id not in self.cooperation_counts:
            self.cooperation_counts[vehicle_id] = 0
        self.cooperation_counts[vehicle_id] += 1
        
    def _handle_negotiation(self, msg):
        """Override to track defection."""
        super()._handle_negotiation(msg)
        
        vehicle_id = msg.sender_id
        if vehicle_id not in self.defection_counts:
            self.defection_counts[vehicle_id] = 0
        self.defection_counts[vehicle_id] += 1
        
    def _process_negotiations(self):
        """Override to add round summary logging."""
        if any(status == "pending" for status in self.pending_responses.values()):
            return  # Still waiting for responses
            
        self._log_round_summary()
        super()._process_negotiations()
        
    def _log_round_summary(self):
        """Log summary of current negotiation round."""
        self.model.log_activity(
            "Orchestrator",
            f"\nROUND {self.negotiation_round} SUMMARY",
            "info"
        )
        
        for vid in sorted(self.current_assignments.keys()):
            sid, qpos = self.current_assignments[vid]
            status = self.pending_responses.get(vid, "unknown")
            
            vehicle = self.model.vehicles.get(vid)
            strategy = ""
            if hasattr(vehicle, 'strategy'):
                strategy = f" [{vehicle.strategy.upper()}]"
            
            if status == "accepted":
                self.model.log_activity(
                    "Orchestrator",
                    f"  {vid}{strategy}: Station_{sid}, Pos={qpos} → ACCEPTED",
                    "success"
                )
            elif status == "negotiating":
                reason = "wants better position"
                for neg in self.negotiations:
                    if neg.sender_id == vid:
                        reason = f"wants pos={neg.desired_queue_position} (reason: {neg.reason})"
                        break
                self.model.log_activity(
                    "Orchestrator",
                    f"  {vid}{strategy}: Station_{sid}, Pos={qpos} → NEGOTIATING ({reason})",
                    "warning"
                )
        
        # Show decision
        if all(status == "accepted" for status in self.pending_responses.values()):
            self.model.log_activity(
                "Orchestrator",
                f"All vehicles accepted → CONSENSUS REACHED!",
                "success"
            )
        else:
            negotiating_count = sum(1 for s in self.pending_responses.values() if s == "negotiating")
            self.model.log_activity(
                "Orchestrator",
                f"{negotiating_count} vehicle(s) negotiating → Continue to Round {self.negotiation_round + 1}",
                "info"
            )
    
    def _broadcast_consensus(self):
        """Override to log behavioral summary."""
        self.model.log_activity(
            "Orchestrator",
            "Behavioral Statistics:",
            "info"
        )
        
        for vid in sorted(self.model.vehicles.keys()):
            cooperations = self.cooperation_counts.get(vid, 0)
            defections = self.defection_counts.get(vid, 0)
            total = cooperations + defections
            
            if total > 0:
                coop_rate = (cooperations / total) * 100
                self.model.log_activity(
                    "Orchestrator",
                    f"  {vid}: Cooperate={cooperations}, Defect={defections}, Rate={coop_rate:.0f}%",
                    "info"
                )
        
        super()._broadcast_consensus()
        
    def get_behavioral_summary(self) -> Dict:
        """Get summary of behavioral patterns."""
        return {
            'cooperation_counts': self.cooperation_counts.copy(),
            'defection_counts': self.defection_counts.copy(),
            'total_rounds': self.negotiation_round,
        }
