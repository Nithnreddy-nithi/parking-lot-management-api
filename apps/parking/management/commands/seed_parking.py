from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.parking.enums import GateType, SpotOperationalStatus, SpotType
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot


class Command(BaseCommand):
    help = "Create idempotent demo parking configuration without changing existing records."

    @transaction.atomic
    def handle(self, *args, **options):
        parking_lot, lot_created = ParkingLot.objects.get_or_create(
            code="DEMO",
            defaults={
                "name": "Demo Parking Lot",
                "address": "Demo address",
                "timezone": "Asia/Kolkata",
                "is_active": True,
            },
        )
        if not parking_lot.is_active:
            raise CommandError(
                "The DEMO parking lot is inactive; activate it before adding missing demo children."
            )

        basement, basement_created = Floor.objects.get_or_create(
            parking_lot=parking_lot,
            code="B1",
            defaults={"name": "Basement 1", "level": -1, "is_active": True},
        )
        ground, ground_created = Floor.objects.get_or_create(
            parking_lot=parking_lot,
            code="G",
            defaults={"name": "Ground Floor", "level": 0, "is_active": True},
        )

        gate_specs = (
            ("ENTRY-1", "Main Entry", GateType.ENTRY),
            ("EXIT-1", "Main Exit", GateType.EXIT),
        )
        gates_created = 0
        for code, name, gate_type in gate_specs:
            _, created = Gate.objects.get_or_create(
                parking_lot=parking_lot,
                code=code,
                defaults={"name": name, "gate_type": gate_type, "is_active": True},
            )
            gates_created += int(created)

        spot_specs = (
            (basement, "B1-M-01", SpotType.MOTORCYCLE, SpotOperationalStatus.ENABLED),
            (basement, "B1-C-01", SpotType.COMPACT, SpotOperationalStatus.ENABLED),
            (basement, "B1-L-01", SpotType.LARGE, SpotOperationalStatus.MAINTENANCE),
            (ground, "G-M-01", SpotType.MOTORCYCLE, SpotOperationalStatus.ENABLED),
            (ground, "G-C-01", SpotType.COMPACT, SpotOperationalStatus.ENABLED),
            (ground, "G-L-01", SpotType.LARGE, SpotOperationalStatus.DISABLED),
        )
        spots_created = 0
        for floor, number, spot_type, operational_status in spot_specs:
            _, created = ParkingSpot.objects.get_or_create(
                floor=floor,
                number=number,
                defaults={
                    "spot_type": spot_type,
                    "operational_status": operational_status,
                },
            )
            spots_created += int(created)

        floors_created = int(basement_created) + int(ground_created)
        self.stdout.write(
            self.style.SUCCESS(
                "Demo parking configuration ready: "
                f"lots created={int(lot_created)}, floors created={floors_created}, "
                f"gates created={gates_created}, spots created={spots_created}. "
                "Existing matching records were preserved."
            )
        )
