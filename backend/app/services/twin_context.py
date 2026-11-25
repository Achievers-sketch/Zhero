"""Build the SIMULATED twin context that accompanies a question about an equipment profile.

Everything here is synthetic; observations are labelled as such and kept apart from
documented facts. Band comparisons use the demo bands, which are illustrative assumptions,
not manufacturer limits.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.digital_twin import config
from app.llm.base import TwinObservation
from app.models.equipment import Equipment
from app.models.twin import EquipmentEvent, Reading, TwinState

# Words appended to the retrieval query when a scenario is active, so the right manual
# sections surface. They only broaden retrieval; they are never presented as findings.
SCENARIO_QUERY_HINTS = {
    "cooling_degradation": "cooling fan speed temperature ventilation",
    "power_instability": "power supply input voltage",
    "component_fault": "component fault inspection",
}


@dataclass
class TwinContext:
    equipment: Equipment
    active_scenario: str | None
    observations: list[TwinObservation] = field(default_factory=list)

    @property
    def retrieval_hint(self) -> str:
        return SCENARIO_QUERY_HINTS.get(self.active_scenario or "", "")


def build_twin_context(db: Session, equipment: Equipment) -> TwinContext:
    state = db.get(TwinState, equipment.id)
    scenario = state.active_scenario if state else None
    obs = [
        TwinObservation(
            "Equipment status",
            f"{equipment.id} ({equipment.manufacturer or 'unknown manufacturer'} "
            f"{equipment.model or 'unknown model'}) simulated status is '{equipment.status}'.",
        )
    ]
    if scenario:
        label = config.SCENARIOS[scenario].label
        obs.append(
            TwinObservation("Active simulated scenario", f"Simulated scenario active: {label}.")
        )
    for comp in equipment.components:
        if comp.status != "normal":
            obs.append(
                TwinObservation(
                    "Component status",
                    f"Simulated component {comp.id} ({comp.name}): {comp.status}.",
                )
            )

    for variable, spec in config.VARIABLES.items():
        reading = db.scalars(
            select(Reading)
            .where(Reading.equipment_id == equipment.id, Reading.variable == variable)
            .order_by(Reading.id.desc())
            .limit(1)
        ).first()
        if reading is None:
            continue
        low, high = config.DEMO_BANDS[variable]
        outside = not (low <= reading.value <= high)
        obs.append(
            TwinObservation(
                "Simulated reading outside demo band" if outside else "Simulated reading",
                f"{variable} = {reading.value:.1f} {spec.unit}"
                + (f" (outside the synthetic demo band {low:g}-{high:g})" if outside else ""),
            )
        )

    events = db.scalars(
        select(EquipmentEvent)
        .where(EquipmentEvent.equipment_id == equipment.id)
        .order_by(EquipmentEvent.id.desc())
        .limit(3)
    ).all()
    for event in events:
        obs.append(TwinObservation("Recent simulated event", event.description))
    return TwinContext(equipment, scenario, obs)
