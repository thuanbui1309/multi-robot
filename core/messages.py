from enum import Enum
from typing import Optional, Tuple, List
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    """Types of messages exchanged between agents."""
    STATUS_UPDATE = "status_update"
    ASSIGNMENT = "assignment"
    ASSIGNMENT_REJECTION = "assignment_rejection"
    ASSIGNMENT_COUNTER_PROPOSAL = "assignment_counter_proposal"
    PATH_REQUEST = "path_request"
    PATH_RESPONSE = "path_response"
    RESERVATION_REQUEST = "reservation_request"
    RESERVATION_RESPONSE = "reservation_response"
    OBSTACLE_ALERT = "obstacle_alert"
    CHARGING_COMPLETE = "charging_complete"
    QUEUE_ASSIGNMENT = "queue_assignment"
    QUEUE_NEGOTIATION = "queue_negotiation"
    ASSIGNMENT_ACCEPTED = "assignment_accepted"
    CONSENSUS_REACHED = "consensus_reached"


class VehicleStatus(str, Enum):
    """Possible states of a vehicle."""
    IDLE = "idle"
    PLANNING = "planning"
    MOVING = "moving"
    CHARGING = "charging"
    STUCK = "stuck"
    EXITING = "exiting"  # Heading to exit after charging complete
    COMPLETED = "completed"  # Reached exit and finished


class Message(BaseModel):
    """Base message class."""
    msg_type: MessageType
    sender_id: str
    receiver_id: Optional[str] = None
    timestamp: int


class StatusUpdateMessage(Message):
    """Vehicle status update to orchestrator."""
    msg_type: MessageType = MessageType.STATUS_UPDATE
    position: Tuple[int, int]
    battery_level: float = Field(ge=0.0, le=100.0)
    status: VehicleStatus
    target_station: Optional[int] = None


class AssignmentMessage(Message):
    """Station assignment from orchestrator to vehicle."""
    msg_type: MessageType = MessageType.ASSIGNMENT
    station_id: int
    station_position: Tuple[int, int]
    priority: int = 0


class PathRequestMessage(Message):
    """Request for path planning."""
    msg_type: MessageType = MessageType.PATH_REQUEST
    start: Tuple[int, int]
    goal: Tuple[int, int]


class PathResponseMessage(Message):
    """Response with planned path."""
    msg_type: MessageType = MessageType.PATH_RESPONSE
    path: List[Tuple[int, int]]
    cost: float
    success: bool


class ReservationRequestMessage(Message):
    """Request to reserve a cell at a specific time."""
    msg_type: MessageType = MessageType.RESERVATION_REQUEST
    position: Tuple[int, int]
    time_step: int
    vehicle_id: str


class ReservationResponseMessage(Message):
    """Response to reservation request."""
    msg_type: MessageType = MessageType.RESERVATION_RESPONSE
    approved: bool
    position: Tuple[int, int]
    time_step: int


class ObstacleAlertMessage(Message):
    """Alert about detected obstacle."""
    msg_type: MessageType = MessageType.OBSTACLE_ALERT
    obstacle_position: Tuple[int, int]
    requires_replan: bool = True


class ChargingCompleteMessage(Message):
    """Notification that charging is complete."""
    msg_type: MessageType = MessageType.CHARGING_COMPLETE
    final_battery: float
    charging_duration: int


class AssignmentRejectionMessage(Message):
    """Vehicle rejects a station assignment with reason."""
    msg_type: MessageType = MessageType.ASSIGNMENT_REJECTION
    rejected_station_id: int
    reason: str  # e.g., "too_far", "low_battery", "prefer_alternative"
    current_position: Tuple[int, int]
    battery_level: float


class AssignmentCounterProposalMessage(Message):
    """Vehicle proposes alternative station assignment."""
    msg_type: MessageType = MessageType.ASSIGNMENT_COUNTER_PROPOSAL
    rejected_station_id: int
    proposed_station_id: int
    reason: str
    current_position: Tuple[int, int]
    battery_level: float


class QueueAssignmentMessage(Message):
    """Queue-based station assignment from orchestrator to vehicle."""
    msg_type: MessageType = MessageType.QUEUE_ASSIGNMENT
    station_id: int
    station_position: Tuple[int, int]
    queue_position: int  # Position in station's queue (0 = first)
    total_in_queue: int  # Total agents assigned to this station
    all_assignments: dict  # {vehicle_id: (station_id, queue_pos)}


class QueueNegotiationMessage(Message):
    """Vehicle negotiates to change queue position."""
    msg_type: MessageType = MessageType.QUEUE_NEGOTIATION
    station_id: int
    current_queue_position: int
    desired_queue_position: int
    reason: str  # e.g., "critical_battery", "closer_position", "urgent_task"
    urgency_score: float = Field(ge=0.0, le=10.0)  # 10 = most urgent


class AssignmentAcceptedMessage(Message):
    """Vehicle accepts the assignment."""
    msg_type: MessageType = MessageType.ASSIGNMENT_ACCEPTED
    station_id: int
    queue_position: int


class ConsensusReachedMessage(Message):
    """Orchestrator broadcasts that consensus is reached."""
    msg_type: MessageType = MessageType.CONSENSUS_REACHED
    final_assignments: dict  # {vehicle_id: (station_id, queue_pos)}
    can_proceed: bool