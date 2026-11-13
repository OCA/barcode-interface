# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestBarcodeStockCycleCount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.location = cls.env["stock.location"].create(
            {
                "name": "Barcode cycle-count test location",
                "location_id": cls.env.ref("stock.stock_location_stock").id,
                "usage": "internal",
                "company_id": cls.company.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Cycle Count Product", "is_storable": True}
        )
        cls.rule = cls.env["stock.cycle.count.rule"].create(
            {"name": "Barcode test rule", "rule_type": "periodic"}
        )

    def make_count(self, state="draft", responsible=False, company=None):
        return self.env["stock.cycle.count"].create(
            {
                "location_id": self.location.id,
                "cycle_count_rule_id": self.rule.id,
                "company_id": (company or self.company).id,
                "responsible_id": responsible and responsible.id or False,
                "state": state,
            }
        )

    def make_inventory(self, count, state="in_progress", quantity=4, counted=4):
        location = count.location_id
        company = count.company_id
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Barcode cycle inventory",
                "cycle_count_id": count.id,
                "company_id": company.id,
                "location_ids": [(6, 0, [location.id])],
                "exclude_sublocation": True,
                "state": state,
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": location.id,
                "company_id": company.id,
                "quantity": quantity,
                "inventory_quantity": counted,
                "barcode_cycle_count_counted": True,
                "current_inventory_id": inventory.id,
                "to_do": True,
            }
        )
        inventory.stock_quant_ids = [(6, 0, [quant.id])]
        return inventory, quant

    def make_unassociated_quant(self, count, product, quantity, lot=False, owner=False):
        values = {
            "product_id": product.id,
            "location_id": count.location_id.id,
            "company_id": count.company_id.id,
            "quantity": quantity,
        }
        if lot:
            values["lot_id"] = lot.id
        if owner:
            values["owner_id"] = owner.id
        return self.env["stock.quant"].create(values)

    def get_other_company(self):
        return self.env["res.company"].search(
            [("id", "!=", self.company.id)], limit=1
        ) or self.env["res.company"].create({"name": "Other test company"})

    def make_line(self, quant, counted_qty, lot_id=False, lot_name=False):
        return {
            "quant_id": quant.id,
            "counted_qty": counted_qty,
            "lot_id": lot_id,
            "lot_name": lot_name,
        }

    def read_cycle_count_line(self, inventory, quant):
        result = self.env["stock.inventory"].barcode_get_cycle_count_lines(inventory.id)
        return next(line for line in result["lines"] if line["quant_id"] == quant.id)

    def make_save_line(self, inventory, quant, counted_qty):
        line = self.read_cycle_count_line(inventory, quant)
        return {
            "quant_id": quant.id,
            "counted_qty": counted_qty,
            "lot_id": line["lot_id"],
            "lot_name": line["lot_name"],
            "write_date": line["write_date"],
        }

    def test_list_scopes_current_company_and_draft_open(self):
        draft = self.make_count()
        opened = self.make_count(state="open")
        self.make_count(state="cancelled")
        result = self.env["stock.cycle.count"].barcode_get_counts()
        ids = {item["id"] for item in result["counts"]}
        self.assertIn(draft.id, ids)
        self.assertIn(opened.id, ids)

    def test_list_defaults_to_current_user_or_unassigned(self):
        other = self.env["res.users"].create(
            {"name": "Other default user", "login": "cycle-default-other"}
        )
        assigned = self.make_count(responsible=self.env.user)
        unassigned = self.make_count()
        other_assigned = self.make_count(responsible=other)
        result = self.env["stock.cycle.count"].barcode_get_counts()
        ids = {item["id"] for item in result["counts"]}
        self.assertTrue({assigned.id, unassigned.id}.issubset(ids))
        self.assertNotIn(other_assigned.id, ids)

    def test_list_show_all_removes_assignment_only(self):
        user = self.env["res.users"].create(
            {"name": "Other cycle user", "login": "cycle-other"}
        )
        count = self.make_count(responsible=user)
        done = self.make_count(state="done", responsible=user)
        cancelled = self.make_count(state="cancelled", responsible=user)
        result = self.env["stock.cycle.count"].barcode_get_counts(show_all=True)
        ids = {item["id"] for item in result["counts"]}
        self.assertIn(count.id, ids)
        self.assertNotIn(done.id, ids)
        self.assertNotIn(cancelled.id, ids)

    def test_cross_company_count_is_invisible(self):
        other = self.get_other_company()
        location = self.env["stock.location"].create(
            {
                "name": "Other internal",
                "usage": "internal",
                "company_id": other.id,
            }
        )
        count = self.env["stock.cycle.count"].create(
            {
                "location_id": location.id,
                "cycle_count_rule_id": self.rule.id,
                "company_id": other.id,
            }
        )
        ids = {
            item["id"]
            for item in self.env["stock.cycle.count"].barcode_get_counts()["counts"]
        }
        self.assertNotIn(count.id, ids)

    def test_matching_location_advances(self):
        count = self.make_count()
        result = self.env["stock.cycle.count"].barcode_validate_location(
            count.id, self.location.id
        )
        self.assertTrue(result["valid"])

    def test_cross_company_location_rejected(self):
        other = self.get_other_company()
        location = self.env["stock.location"].create(
            {"name": "Other location", "usage": "internal", "company_id": other.id}
        )
        count = self.make_count()
        with self.assertRaises(UserError):
            self.env["stock.cycle.count"].barcode_validate_location(
                count.id, location.id
            )

    def test_confirm_calls_oca_action_and_requires_in_progress(self):
        count = self.make_count()
        with patch.object(
            type(count), "action_create_inventory_adjustment"
        ) as create_adjustment:
            with self.assertRaises(UserError):
                self.env["stock.cycle.count"].barcode_confirm(count.id)
        create_adjustment.assert_called_once()

    def test_confirm_creates_exactly_one_linked_adjustment(self):
        count = self.make_count()
        result = self.env["stock.cycle.count"].barcode_confirm(count.id)
        count.invalidate_recordset()
        self.assertEqual(len(count.stock_adjustment_ids), 1)
        self.assertEqual(result["inventory"]["id"], count.stock_adjustment_ids.id)
        self.assertEqual(count.stock_adjustment_ids.state, "in_progress")

    def test_confirm_new_count_prefills_counted_with_theoretical(self):
        self.company.inventory_adjustment_counted_quantities = "counted"
        count = self.make_count()
        quant = self.make_unassociated_quant(count, self.product, quantity=6)

        self.env["stock.cycle.count"].barcode_confirm(count.id)

        count.invalidate_recordset(["stock_adjustment_ids"])
        quant.invalidate_recordset(["current_inventory_id", "inventory_quantity"])
        inventory = count.stock_adjustment_ids
        self.assertEqual(inventory.prefill_counted_quantity, "counted")
        self.assertEqual(quant.current_inventory_id, inventory)
        self.assertEqual(quant.quantity, 6)
        self.assertEqual(quant.inventory_quantity, 6)

    def test_confirm_new_count_prefills_zero_without_changing_theoretical(self):
        self.company.inventory_adjustment_counted_quantities = "zero"
        count = self.make_count()
        quant = self.make_unassociated_quant(count, self.product, quantity=6)

        self.env["stock.cycle.count"].barcode_confirm(count.id)

        count.invalidate_recordset(["stock_adjustment_ids"])
        quant.invalidate_recordset(["current_inventory_id", "inventory_quantity"])
        inventory = count.stock_adjustment_ids
        self.assertEqual(inventory.prefill_counted_quantity, "zero")
        self.assertEqual(quant.current_inventory_id, inventory)
        self.assertEqual(quant.quantity, 6)
        self.assertEqual(quant.inventory_quantity, 0)

    def test_confirm_open_reuses_in_progress_adjustment(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        result = self.env["stock.cycle.count"].barcode_confirm(count.id)
        self.assertEqual(result["inventory"]["id"], inventory.id)
        self.assertEqual(inventory.state, "in_progress")

    def test_confirm_open_preserves_existing_count_progress(self):
        self.company.inventory_adjustment_counted_quantities = "counted"
        count = self.make_count()
        quant = self.make_unassociated_quant(count, self.product, quantity=6)
        self.env["stock.cycle.count"].barcode_confirm(count.id)
        count.invalidate_recordset(["stock_adjustment_ids"])
        inventory = count.stock_adjustment_ids
        quant.inventory_quantity = 2.5
        self.company.inventory_adjustment_counted_quantities = "zero"

        result = self.env["stock.cycle.count"].barcode_confirm(count.id)

        self.assertEqual(result["inventory"]["id"], inventory.id)
        self.assertEqual(count.stock_adjustment_ids, inventory)
        self.assertEqual(len(count.stock_adjustment_ids), 1)
        self.assertEqual(inventory.state, "in_progress")
        self.assertEqual(quant.quantity, 6)
        self.assertEqual(quant.inventory_quantity, 2.5)

    def test_confirm_open_starts_draft_adjustment(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count, state="draft")
        result = self.env["stock.cycle.count"].barcode_confirm(count.id)
        self.assertEqual(result["inventory"]["id"], inventory.id)
        self.assertEqual(inventory.state, "in_progress")

    def test_confirm_open_rejects_broken_adjustment_linkage(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        inventory.cycle_count_id = False
        with self.assertRaisesRegex(UserError, "no linked adjustment"):
            self.env["stock.cycle.count"].barcode_confirm(count.id)

    def test_confirm_failure_leaves_no_second_adjustment(self):
        count = self.make_count()
        inventory, _quant = self.make_inventory(count, state="draft")
        with patch.object(
            type(inventory),
            "action_state_to_in_progress",
            side_effect=UserError("start failed"),
        ):
            with self.assertRaises(UserError):
                self.env["stock.cycle.count"].barcode_confirm(count.id)
        self.assertEqual(len(count.stock_adjustment_ids), 1)

    def test_concurrent_in_progress_adjustment_is_surfaced_as_error(self):
        count = self.make_count()
        with patch.object(
            type(count),
            "action_create_inventory_adjustment",
            side_effect=ValidationError("An adjustment is already in progress."),
        ):
            with self.assertRaisesRegex(ValidationError, "already in progress"):
                self.env["stock.cycle.count"].barcode_confirm(count.id)

    def test_non_in_progress_result_does_not_open_count_screen(self):
        count = self.make_count()
        inventory, _quant = self.make_inventory(count, state="draft")
        with patch.object(type(inventory), "action_state_to_in_progress"):
            with self.assertRaises(UserError):
                self.env["stock.cycle.count"].barcode_confirm(count.id)
        self.assertEqual(inventory.state, "draft")

    def test_unknown_location_scan_rejected(self):
        count = self.make_count()
        with self.assertRaises(UserError):
            self.env["stock.cycle.count"].barcode_validate_location(count.id, 0)

    def test_read_uses_linked_adjustment_quant_lines(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        result = self.env["stock.inventory"].barcode_get_cycle_count_lines(inventory.id)
        self.assertEqual(result["lines"][0]["quant_id"], quant.id)

    def test_scan_matching_product_updates_line(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        result = self.env["stock.inventory"].barcode_get_cycle_count_lines(inventory.id)
        line = next(
            item for item in result["lines"] if item["product_id"] == self.product.id
        )
        self.assertEqual(line["quant_id"], quant.id)
        self.assertEqual(line["product_name"], self.product.display_name)

    def test_add_cycle_count_quant_uses_zero_prefill_and_is_idempotent(self):
        product = self.env["product.product"].create(
            {"name": "Late theoretical-prefill product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, original_quant = self.make_inventory(count)
        inventory.prefill_counted_quantity = "zero"
        quant = self.make_unassociated_quant(count, product, quantity=7)

        result = self.env["stock.inventory"].barcode_add_cycle_count_quant(
            inventory.id, product.id
        )

        self.assertEqual(
            set(result),
            {
                "quant_id",
                "product_id",
                "product_name",
                "tracking",
                "lot_id",
                "lot_name",
                "theoretical_qty",
                "counted_qty",
                "barcode_cycle_count_counted",
                "difference",
                "uom",
                "rounding",
                "write_date",
            },
        )
        self.assertEqual(result["quant_id"], quant.id)
        self.assertEqual(result["theoretical_qty"], 7)
        self.assertEqual(result["counted_qty"], 0)
        self.assertEqual(quant.quantity, 7)
        self.assertEqual(quant.inventory_quantity, 0)
        self.assertTrue(quant.barcode_cycle_count_counted)
        self.assertEqual(quant.current_inventory_id, inventory)
        self.assertIn(quant, inventory.stock_quant_ids)
        self.assertEqual(count.stock_adjustment_ids, inventory)
        self.assertEqual(original_quant.quantity, 4)

        quant.inventory_quantity = 2.5
        repeated = self.env["stock.inventory"].barcode_add_cycle_count_quant(
            inventory.id, product.id
        )
        self.assertEqual(repeated["quant_id"], quant.id)
        self.assertEqual(repeated["counted_qty"], 2.5)
        self.assertEqual(quant.inventory_quantity, 2.5)
        self.assertTrue(quant.barcode_cycle_count_counted)
        self.assertEqual(
            len(inventory.stock_quant_ids.filtered(lambda item: item == quant)), 1
        )
        self.assertEqual(len(count.stock_adjustment_ids), 1)

    def test_add_cycle_count_quant_uses_counted_prefill(self):
        product = self.env["product.product"].create(
            {"name": "Late counted-prefill product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, _original_quant = self.make_inventory(count)
        inventory.prefill_counted_quantity = "counted"
        quant = self.make_unassociated_quant(count, product, quantity=7)

        result = self.env["stock.inventory"].barcode_add_cycle_count_quant(
            inventory.id, product.id
        )

        self.assertEqual(result["theoretical_qty"], 7)
        self.assertEqual(result["counted_qty"], 7)
        self.assertEqual(quant.quantity, 7)
        self.assertEqual(quant.inventory_quantity, 7)
        self.assertEqual(quant.current_inventory_id, inventory)
        self.assertTrue(quant.barcode_cycle_count_counted)

    def test_add_cycle_count_quant_fails_closed_without_unique_quant(self):
        product = self.env["product.product"].create(
            {"name": "Unquantified product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, original_quant = self.make_inventory(count)

        with self.assertRaisesRegex(
            UserError,
            "No existing stock quant matches the selected product identity",
        ):
            self.env["stock.inventory"].barcode_add_cycle_count_quant(
                inventory.id, product.id
            )
        self.assertEqual(inventory.stock_quant_ids, original_quant)
        self.assertFalse(
            self.env["stock.quant"].search(
                [
                    ("product_id", "=", product.id),
                    ("location_id", "=", self.location.id),
                ]
            )
        )
        self.assertEqual(inventory.state, "in_progress")
        self.assertEqual(len(count.stock_adjustment_ids), 1)

        first_owner = self.env.user.partner_id
        second_owner = self.env["res.partner"].create({"name": "Other quant owner"})
        first = self.make_unassociated_quant(
            count, product, quantity=3, owner=first_owner
        )
        second = self.make_unassociated_quant(
            count, product, quantity=4, owner=second_owner
        )
        with self.assertRaisesRegex(
            UserError,
            "Multiple existing stock quants match the selected product identity",
        ):
            self.env["stock.inventory"].barcode_add_cycle_count_quant(
                inventory.id, product.id
            )
        self.assertEqual(inventory.stock_quant_ids, original_quant)
        self.assertFalse(first.current_inventory_id)
        self.assertFalse(second.current_inventory_id)
        self.assertFalse(first.to_do)
        self.assertFalse(second.to_do)
        self.assertFalse(first.barcode_cycle_count_counted)
        self.assertFalse(second.barcode_cycle_count_counted)
        self.assertEqual(first.inventory_quantity, 0)
        self.assertEqual(second.inventory_quantity, 0)
        self.assertNotIn(first, inventory.stock_quant_ids)
        self.assertNotIn(second, inventory.stock_quant_ids)
        self.assertEqual(inventory.state, "in_progress")
        self.assertEqual(len(count.stock_adjustment_ids), 1)

    def test_add_cycle_count_quant_preserves_existing_lot_and_serial(self):
        lot_product = self.env["product.product"].create(
            {"name": "Late lot product", "is_storable": True, "tracking": "lot"}
        )
        serial_product = self.env["product.product"].create(
            {
                "name": "Late serial product",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        lot = self.env["stock.lot"].create(
            {
                "name": "LATE-LOT-1",
                "product_id": lot_product.id,
                "company_id": self.company.id,
            }
        )
        serial = self.env["stock.lot"].create(
            {
                "name": "LATE-SERIAL-1",
                "product_id": serial_product.id,
                "company_id": self.company.id,
            }
        )
        wrong_product = self.env["product.product"].create(
            {
                "name": "Other tracked product",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        wrong_lot = self.env["stock.lot"].create(
            {
                "name": "WRONG-PRODUCT-LOT",
                "product_id": wrong_product.id,
                "company_id": self.company.id,
            }
        )
        count = self.make_count(state="open")
        inventory, _original_quant = self.make_inventory(count)
        lot_quant = self.make_unassociated_quant(count, lot_product, 5, lot=lot)
        serial_quant = self.make_unassociated_quant(
            count, serial_product, 1, lot=serial
        )
        lot_count = self.env["stock.lot"].search_count([])

        lot_line = self.env["stock.inventory"].barcode_add_cycle_count_quant(
            inventory.id, lot_product.id, lot.id
        )
        serial_line = self.env["stock.inventory"].barcode_add_cycle_count_quant(
            inventory.id, serial_product.id, serial.id
        )

        self.assertEqual(lot_line["lot_id"], lot.id)
        self.assertEqual(lot_line["lot_name"], lot.name)
        self.assertEqual(serial_line["lot_id"], serial.id)
        self.assertEqual(serial_line["lot_name"], serial.name)
        self.assertEqual(lot_quant.lot_id, lot)
        self.assertEqual(serial_quant.lot_id, serial)
        self.assertEqual(self.env["stock.lot"].search_count([]), lot_count)

        for supplied_lot_id in (999999, wrong_lot.id, False):
            with self.assertRaises(UserError):
                self.env["stock.inventory"].barcode_add_cycle_count_quant(
                    inventory.id, lot_product.id, supplied_lot_id
                )
        self.assertEqual(self.env["stock.lot"].search_count([]), lot_count)
        self.assertEqual(lot_quant.current_inventory_id, inventory)
        self.assertEqual(lot_quant.lot_id, lot)
        self.assertEqual(len(count.stock_adjustment_ids), 1)

    def test_add_cycle_count_quant_rejects_invalid_products_and_non_open_count(self):
        service = self.env["product.product"].create(
            {"name": "Non-storable service", "type": "service"}
        )
        count = self.make_count(state="draft")
        inventory, original_quant = self.make_inventory(count)
        product = self.env["product.product"].create(
            {"name": "Late product", "is_storable": True}
        )
        quant = self.make_unassociated_quant(count, product, quantity=6)

        for product_id in (999999, service.id):
            with self.assertRaises(UserError):
                self.env["stock.inventory"].barcode_add_cycle_count_quant(
                    inventory.id, product_id
                )
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_add_cycle_count_quant(
                inventory.id, product.id
            )
        self.assertEqual(inventory.stock_quant_ids, original_quant)
        self.assertFalse(quant.current_inventory_id)
        self.assertEqual(len(count.stock_adjustment_ids), 1)

    def test_scan_outside_adjustment_rejected(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        outside = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 2,
                "current_inventory_id": inventory.id,
            }
        )
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(outside, 1)]
            )
        self.assertEqual(quant.inventory_quantity, 4)

    def test_tracked_product_without_lot_rejected(self):
        product = self.env["product.product"].create(
            {"name": "Tracked cycle product", "is_storable": True, "tracking": "lot"}
        )
        count = self.make_count(state="open")
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Tracked barcode inventory",
                "cycle_count_id": count.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 1,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(6, 0, [quant.id])]
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(quant, 1)]
            )

    def test_serial_quantity_greater_than_one_rejected(self):
        product = self.env["product.product"].create(
            {"name": "Serial cycle product", "is_storable": True, "tracking": "serial"}
        )
        lot = self.env["stock.lot"].create(
            {
                "name": "SERIAL-1",
                "product_id": product.id,
                "company_id": self.company.id,
            }
        )
        count = self.make_count(state="open")
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Serial barcode inventory",
                "cycle_count_id": count.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "lot_id": lot.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 1,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(6, 0, [quant.id])]
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(quant, 2, lot.id, lot.name)]
            )

    def test_company_and_quant_ids_revalidated(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        quant.current_inventory_id = False
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(quant, 3)]
            )

    def test_duplicate_quant_ids_are_rejected_before_writes(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        with self.assertRaisesRegex(UserError, "more than once"):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id,
                [self.make_line(quant, 3), self.make_line(quant, 3)],
            )
        self.assertEqual(quant.inventory_quantity, 4)
        self.assertEqual(inventory.state, "in_progress")

    def test_unknown_quant_id_is_rejected_before_writes(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        with self.assertRaisesRegex(UserError, "not linked"):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id,
                [
                    self.make_line(quant, 4),
                    {
                        "quant_id": 999999,
                        "counted_qty": 1,
                        "lot_id": False,
                        "lot_name": False,
                    },
                ],
            )
        self.assertEqual(quant.inventory_quantity, 4)
        self.assertEqual(inventory.state, "in_progress")

    def test_foreign_quant_is_rejected_before_writes(self):
        other = self.get_other_company()
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        foreign_product = self.env["product.product"].create(
            {
                "name": "Foreign quant product",
                "is_storable": True,
                "company_id": other.id,
            }
        )
        foreign = self.env["stock.quant"].create(
            {
                "product_id": foreign_product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 2,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(4, foreign.id)]
        with self.assertRaisesRegex(UserError, "no longer valid"):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id,
                [self.make_line(quant, 4), self.make_line(foreign, 2)],
            )
        self.assertEqual(quant.inventory_quantity, 4)
        self.assertEqual(foreign.inventory_quantity, 0)
        self.assertEqual(inventory.state, "in_progress")

    def test_negative_quantity_rejected(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(quant, -1)]
            )

    def test_non_finite_quantity_rejected(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        for counted_qty in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaisesRegex(UserError, "must be finite"):
                self.env["stock.inventory"].barcode_apply_cycle_count(
                    inventory.id, [self.make_line(quant, counted_qty)]
                )
        self.assertEqual(quant.inventory_quantity, 4)
        self.assertEqual(inventory.state, "in_progress")

    def test_zero_difference_lines_never_applied(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        with patch.object(type(quant), "action_apply_inventory") as apply:
            result = self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id,
                [self.make_line(quant, quant.quantity)],
                confirm_zero=True,
            )
        self.assertFalse(apply.called)
        self.assertEqual(result["applied_quant_ids"], [])
        self.assertEqual(inventory.state, "done")

    def test_apply_sends_only_non_zero_difference_lines(self):
        count = self.make_count(state="open")
        inventory, zero_quant = self.make_inventory(count)
        changed_quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 2,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(4, changed_quant.id)]
        with patch.object(
            type(zero_quant), "action_apply_inventory", autospec=True
        ) as apply:
            apply.return_value = None
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id,
                [
                    self.make_line(zero_quant, 4),
                    self.make_line(changed_quant, 3),
                ],
            )
        self.assertEqual(apply.call_count, 1)
        self.assertEqual(apply.call_args.args[0].id, changed_quant.id)

    def test_positive_and_negative_differences_apply(self):
        count = self.make_count(state="open")
        inventory, positive = self.make_inventory(count, quantity=4, counted=4)
        negative = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 6,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(4, negative.id)]
        with patch.object(
            type(positive), "action_apply_inventory", return_value=None
        ) as apply:
            result = self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id,
                [
                    self.make_line(positive, 5),
                    self.make_line(negative, 3),
                ],
            )
        self.assertEqual(result["applied_count"], 2)
        self.assertEqual(apply.call_count, 2)

    def test_apply_conflict_action_prevents_completion(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        conflict = {"type": "ir.actions.act_window", "name": "Conflict"}
        with patch.object(
            type(quant), "action_apply_inventory", return_value=conflict
        ) as apply:
            with self.assertRaisesRegex(UserError, "Resolve the conflict"):
                self.env["stock.inventory"].barcode_apply_cycle_count(
                    inventory.id, [self.make_line(quant, 5)]
                )
        apply.assert_called_once()
        self.assertEqual(inventory.state, "in_progress")

    def test_apply_real_outdated_quant_is_rejected_by_barcode_wrapper(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count, quantity=7, counted=5)
        # A barcode count marks the quant as explicitly counted and stores the
        # count snapshot before any later stock movement.
        quant.inventory_quantity_set = True
        quant.flush_recordset()
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.location, quantity=-3
        )

        # Only the on-hand quantity moved; the count snapshot must be preserved
        # so the quant is detected as outdated.
        quant.invalidate_recordset(["quantity"])
        self.assertEqual(quant.quantity, 4)
        self.assertEqual(quant.inventory_quantity, 5)
        self.assertEqual(quant.inventory_diff_quantity, -2)
        self.assertTrue(quant.is_outdated)

        with self.assertRaisesRegex(
            UserError, "Resolve the conflict in the inventory adjustment"
        ):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(quant, 5)]
            )

        self.assertEqual(quant.quantity, 4)
        self.assertEqual(quant.inventory_quantity, 5)
        self.assertEqual(inventory.state, "in_progress")
        self.assertEqual(count.state, "open")

    def test_all_zero_difference_requires_confirmation(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id,
                [self.make_line(quant, quant.quantity)],
            )

    def test_incomplete_non_empty_payload_is_rejected_before_writes(self):
        count = self.make_count(state="open")
        inventory, first = self.make_inventory(count)
        second = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 2,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(4, second.id)]
        with self.assertRaisesRegex(UserError, "Every linked line"):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(first, 5)]
            )
        self.assertEqual(first.inventory_quantity, 4)
        self.assertEqual(second.inventory_quantity, 0)
        self.assertEqual(inventory.state, "in_progress")

    def test_tracked_identity_mismatch_is_rejected_before_writes(self):
        product = self.env["product.product"].create(
            {"name": "Lot cycle product", "is_storable": True, "tracking": "lot"}
        )
        lot = self.env["stock.lot"].create(
            {"name": "LOT-1", "product_id": product.id, "company_id": self.company.id}
        )
        wrong_lot = self.env["stock.lot"].create(
            {"name": "LOT-2", "product_id": product.id, "company_id": self.company.id}
        )
        count = self.make_count(state="open")
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Tracked barcode inventory",
                "cycle_count_id": count.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "lot_id": lot.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 1,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(6, 0, [quant.id])]
        with self.assertRaisesRegex(UserError, "lot or serial"):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [self.make_line(quant, 2, wrong_lot.id, wrong_lot.name)]
            )
        self.assertEqual(quant.inventory_quantity, 0)
        self.assertEqual(inventory.state, "in_progress")

    def test_tracked_identity_match_can_complete(self):
        product = self.env["product.product"].create(
            {"name": "Matching lot product", "is_storable": True, "tracking": "lot"}
        )
        lot = self.env["stock.lot"].create(
            {
                "name": "LOT-MATCH",
                "product_id": product.id,
                "company_id": self.company.id,
            }
        )
        count = self.make_count(state="open")
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Matching lot inventory",
                "cycle_count_id": count.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "lot_id": lot.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 1,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(6, 0, [quant.id])]
        result = self.env["stock.inventory"].barcode_close_cycle_count(
            inventory.id,
            [self.make_line(quant, 1, lot.id, lot.name)],
            confirm_zero=True,
        )
        self.assertEqual(result["applied_count"], 0)
        self.assertEqual(inventory.state, "done")

    def test_empty_adjustment_requires_explicit_zero_confirmation(self):
        count = self.make_count(state="open")
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Empty barcode cycle inventory",
                "cycle_count_id": count.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_close_cycle_count(inventory.id, [])

    def test_close_incomplete_payload_is_rejected_before_writes(self):
        count = self.make_count(state="open")
        inventory, first = self.make_inventory(count)
        second = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 2,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(4, second.id)]
        with self.assertRaisesRegex(UserError, "Every linked line"):
            self.env["stock.inventory"].barcode_close_cycle_count(
                inventory.id,
                [self.make_line(first, 4)],
                confirm_zero=True,
            )
        self.assertEqual(first.inventory_quantity, 4)
        self.assertEqual(second.inventory_quantity, 0)
        self.assertEqual(inventory.state, "in_progress")

    def test_empty_location_zero_confirmation_closes_without_apply(self):
        count = self.make_count(state="open")
        inventory = self.env["stock.inventory"].create(
            {
                "name": "Empty barcode cycle inventory",
                "cycle_count_id": count.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        result = self.env["stock.inventory"].barcode_close_cycle_count(
            inventory.id, [], confirm_zero=True
        )
        self.assertEqual(result["applied_count"], 0)
        self.assertEqual(inventory.state, "done")

    def test_close_calls_oca_done_and_cycle_is_done_with_accuracy(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        self.env["stock.inventory"].barcode_close_cycle_count(
            inventory.id, [self.make_line(_quant, _quant.quantity)], confirm_zero=True
        )
        self.assertEqual(inventory.state, "done")
        self.assertEqual(count.state, "done")

    def test_partial_save_round_trips_zero_fraction_and_null(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        second_product = self.env["product.product"].create(
            {"name": "Unchanged partial-save product", "is_storable": True}
        )
        second_quant = self.make_unassociated_quant(count, second_product, quantity=9)
        second_quant.write(
            {
                "current_inventory_id": inventory.id,
                "to_do": True,
                "inventory_quantity": 8,
                "barcode_cycle_count_counted": True,
            }
        )
        inventory.write({"stock_quant_ids": [(4, second_quant.id)]})
        original_theoretical = quant.quantity
        original_moves = inventory.stock_move_ids.ids

        for counted_qty in (0, 2.5, None):
            payload = self.make_save_line(inventory, quant, counted_qty)
            acknowledgement = self.env["stock.inventory"].barcode_save_cycle_count_line(
                inventory.id, payload
            )
            self.assertEqual(acknowledgement["quant_id"], quant.id)
            self.assertEqual(acknowledgement["counted_qty"], counted_qty)
            self.assertEqual(
                acknowledgement["barcode_cycle_count_counted"],
                counted_qty is not None,
            )
            self.assertTrue(acknowledgement["write_date"])

            saved_line = self.read_cycle_count_line(inventory, quant)
            self.assertEqual(saved_line["counted_qty"], counted_qty)
            self.assertEqual(
                saved_line["barcode_cycle_count_counted"],
                counted_qty is not None,
            )

        self.assertEqual(quant.inventory_quantity, 2.5)
        self.assertEqual(quant.quantity, original_theoretical)
        self.assertEqual(second_quant.inventory_quantity, 8)
        self.assertTrue(second_quant.barcode_cycle_count_counted)
        self.assertEqual(inventory.state, "in_progress")
        self.assertEqual(count.state, "open")
        self.assertEqual(count.stock_adjustment_ids, inventory)
        self.assertEqual(inventory.stock_move_ids.ids, original_moves)

    def test_partial_save_is_idempotent_and_rejects_stale_overwrite(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count, counted=2.5)
        quant.write(
            {
                "inventory_quantity": 2.5,
                "barcode_cycle_count_counted": True,
            }
        )
        payload = self.make_save_line(inventory, quant, 2.5)
        current_revision = self.read_cycle_count_line(inventory, quant)["write_date"]

        acknowledgement = self.env["stock.inventory"].barcode_save_cycle_count_line(
            inventory.id, payload
        )
        self.assertEqual(acknowledgement["counted_qty"], 2.5)
        self.assertEqual(acknowledgement["write_date"], current_revision)

        stale_retry = dict(payload, write_date="2000-01-01 00:00:00.000000")
        acknowledgement = self.env["stock.inventory"].barcode_save_cycle_count_line(
            inventory.id, stale_retry
        )
        self.assertEqual(acknowledgement["counted_qty"], 2.5)
        self.assertEqual(acknowledgement["write_date"], current_revision)

        stale_value = dict(stale_retry, counted_qty=3.5)
        with self.assertRaisesRegex(UserError, "changed"):
            self.env["stock.inventory"].barcode_save_cycle_count_line(
                inventory.id, stale_value
            )
        self.assertEqual(quant.inventory_quantity, 2.5)

    def test_partial_save_rejects_malformed_and_unlinked_payloads(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        payload = self.make_save_line(inventory, quant, 2.5)
        invalid_payloads = [
            dict(payload, unexpected=True),
            {key: value for key, value in payload.items() if key != "counted_qty"},
            dict(payload, counted_qty=True),
            dict(payload, counted_qty="2.5"),
            dict(payload, counted_qty=float("nan")),
            dict(payload, counted_qty=float("inf")),
            dict(payload, counted_qty=-0.1),
            dict(payload, write_date="not-a-revision"),
            [payload, payload],
        ]
        for invalid_payload in invalid_payloads:
            with self.subTest(payload=invalid_payload):
                with self.assertRaises(UserError):
                    self.env["stock.inventory"].barcode_save_cycle_count_line(
                        inventory.id, invalid_payload
                    )

        other_product = self.env["product.product"].create(
            {"name": "Unlinked partial-save product", "is_storable": True}
        )
        unlinked_quant = self.make_unassociated_quant(count, other_product, quantity=1)
        unlinked_payload = dict(payload, quant_id=unlinked_quant.id)
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_save_cycle_count_line(
                inventory.id, unlinked_payload
            )
        self.assertEqual(quant.inventory_quantity, 4)

    def test_partial_save_checks_serial_quantity_and_authoritative_lot(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        product = self.env["product.product"].create(
            {
                "name": "Serial partial-save product",
                "is_storable": True,
                "tracking": "serial",
            }
        )
        lot = self.env["stock.lot"].create(
            {
                "name": "SERIAL-PARTIAL-1",
                "product_id": product.id,
                "company_id": self.company.id,
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "lot_id": lot.id,
                "quantity": 1,
                "inventory_quantity": 1,
                "barcode_cycle_count_counted": True,
                "current_inventory_id": inventory.id,
                "to_do": True,
            }
        )
        inventory.write({"stock_quant_ids": [(4, quant.id)]})
        payload = self.make_save_line(inventory, quant, 2)

        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_save_cycle_count_line(
                inventory.id, payload
            )

        wrong_lot = dict(payload, lot_name="NOT-THE-AUTHORITATIVE-SERIAL")
        wrong_lot["counted_qty"] = 1
        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_save_cycle_count_line(
                inventory.id, wrong_lot
            )
        self.assertEqual(quant.inventory_quantity, 1)

    def test_partial_cycle_count_read_and_save_require_access(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        payload = self.make_save_line(inventory, quant, 2.5)
        user = self.env["res.users"].create(
            {
                "name": "No cycle count access",
                "login": "cycle-count-no-access",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )

        with self.assertRaises(UserError):
            self.env["stock.inventory"].with_user(user).barcode_get_cycle_count_lines(
                inventory.id
            )
        with self.assertRaises(UserError):
            self.env["stock.inventory"].with_user(user).barcode_save_cycle_count_line(
                inventory.id, payload
            )
        self.assertEqual(quant.inventory_quantity, 4)

    def test_partial_cycle_count_read_rejects_inactive_company(self):
        other_company = self.get_other_company()
        other_location = self.env["stock.location"].create(
            {
                "name": "Other-company cycle location",
                "usage": "internal",
                "company_id": other_company.id,
            }
        )
        count = self.env["stock.cycle.count"].create(
            {
                "location_id": other_location.id,
                "cycle_count_rule_id": self.rule.id,
                "company_id": other_company.id,
                "state": "open",
            }
        )
        inventory, _quant = self.make_inventory(count)

        with self.assertRaises(UserError):
            self.env["stock.inventory"].barcode_get_cycle_count_lines(inventory.id)

    def test_confirm_rejects_unknown_and_invalid_counts(self):
        cycle_model = self.env["stock.cycle.count"]
        with self.assertRaisesRegex(UserError, "no longer available"):
            cycle_model.barcode_confirm(999999)

        with self.assertRaisesRegex(UserError, "planned or open"):
            cycle_model.barcode_confirm(self.make_count(state="done").id)

    def test_confirm_rejects_location_from_other_company(self):
        other = self.env["res.company"].create({"name": "Cycle confirm other company"})
        other_location = self.env["stock.location"].create(
            {
                "name": "Other-company confirm location",
                "usage": "internal",
                "company_id": other.id,
            }
        )
        count = self.make_count()
        count.location_id = other_location.id
        with self.assertRaisesRegex(UserError, "location is no longer valid"):
            self.env["stock.cycle.count"].barcode_confirm(count.id)

    def test_confirm_rejects_multiple_adjustments(self):
        count = self.make_count(state="open")
        self.make_inventory(count)
        self.env["stock.inventory"].create(
            {
                "name": "Second cycle adjustment",
                "cycle_count_id": count.id,
                "company_id": self.company.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        with self.assertRaisesRegex(UserError, "more than one adjustment"):
            self.env["stock.cycle.count"].barcode_confirm(count.id)

    def test_confirm_rejects_inconsistent_adjustment(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        # The ORM constraint blocks inconsistent links, so simulate legacy
        # data by removing the inventory location relation.
        location_field = inventory._fields["location_ids"]
        self.env.cr.execute(
            f"DELETE FROM {location_field.relation} "
            f"WHERE {location_field.column1} = %s",
            (inventory.id,),
        )
        inventory.invalidate_recordset(["location_ids"])
        with self.assertRaisesRegex(UserError, "inconsistent"):
            self.env["stock.cycle.count"].barcode_confirm(count.id)

    def test_validate_location_rejects_unknown_count(self):
        with self.assertRaisesRegex(UserError, "no longer available"):
            self.env["stock.cycle.count"].barcode_validate_location(
                999999, self.location.id
            )

    def test_partial_count_rejects_invalid_inventory_scope(self):
        inventory_model = self.env["stock.inventory"]
        for inventory_id in (0, -1, True, "1"):
            with self.subTest(inventory_id=inventory_id):
                with self.assertRaisesRegex(UserError, "unavailable"):
                    inventory_model.barcode_get_cycle_count_lines(inventory_id)
        with self.assertRaisesRegex(UserError, "unavailable"):
            inventory_model.barcode_get_cycle_count_lines(999999)

        plain = inventory_model.create(
            {
                "name": "No cycle count adjustment",
                "company_id": self.company.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        with self.assertRaisesRegex(UserError, "unavailable"):
            inventory_model.barcode_get_cycle_count_lines(plain.id)

    def test_partial_count_rejects_non_open_cycle(self):
        count = self.make_count(state="done")
        inventory, _quant = self.make_inventory(count)
        with self.assertRaisesRegex(UserError, "no longer valid"):
            self.env["stock.inventory"].barcode_get_cycle_count_lines(inventory.id)

    def test_write_date_token_handles_empty_values(self):
        token = self.env["stock.inventory"]._barcode_write_date_token
        self.assertFalse(token(False))
        self.assertFalse(token(None))

    def test_partial_count_payload_rejects_invalid_fields(self):
        count = self.make_count(state="open")
        _inventory, quant = self.make_inventory(count)
        write_date = self.env["stock.inventory"]._barcode_write_date_token(
            quant.write_date
        )
        base = {
            "quant_id": quant.id,
            "counted_qty": 1,
            "lot_id": False,
            "lot_name": False,
            "write_date": write_date,
        }
        validate = self.env["stock.inventory"]._barcode_validate_partial_count_payload
        for lot_id in (0, True):
            with self.subTest(lot_id=lot_id):
                with self.assertRaisesRegex(UserError, "payload is invalid"):
                    validate(dict(base, lot_id=lot_id), {quant.id})
        with self.assertRaisesRegex(UserError, "payload is invalid"):
            validate(dict(base, lot_name=5), {quant.id})
        for invalid_write_date in (
            5,
            "2020-01-01",
            "2020-01-01T00:00:00+00:00",
        ):
            with self.subTest(write_date=invalid_write_date):
                with self.assertRaisesRegex(UserError, "revision is invalid"):
                    validate(dict(base, write_date=invalid_write_date), {quant.id})
        with self.assertRaisesRegex(UserError, "quantity is invalid"):
            validate(dict(base, counted_qty=10**400), {quant.id})

    def test_lock_partial_count_rejects_missing_row(self):
        with self.assertRaisesRegex(UserError, "no longer valid"):
            self.env["stock.inventory"]._barcode_lock_partial_count_quant(
                self.env["stock.quant"].browse(999999)
            )

    def test_validate_inventory_rejects_unknown_and_draft(self):
        inventory_model = self.env["stock.inventory"]
        with self.assertRaisesRegex(UserError, "unavailable"):
            inventory_model.barcode_apply_cycle_count(999999, [])
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count, state="draft")
        with self.assertRaisesRegex(UserError, "no longer valid"):
            inventory_model.barcode_apply_cycle_count(inventory.id, [])

    def test_add_quant_rejects_invalid_scope(self):
        product = self.env["product.product"].create(
            {"name": "Add scope product", "is_storable": True}
        )
        inventory_model = self.env["stock.inventory"]
        with self.assertRaisesRegex(UserError, "unavailable"):
            inventory_model.barcode_add_cycle_count_quant(999999, product.id)

        plain = inventory_model.create(
            {
                "name": "No cycle add adjustment",
                "company_id": self.company.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        with self.assertRaisesRegex(UserError, "no longer valid"):
            inventory_model.barcode_add_cycle_count_quant(plain.id, product.id)

    def test_add_quant_wraps_access_errors(self):
        product = self.env["product.product"].create(
            {"name": "Access add product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        with patch.object(
            type(self.env["stock.inventory"]),
            "check_access",
            side_effect=AccessError("denied"),
        ):
            with self.assertRaisesRegex(UserError, "unavailable"):
                self.env["stock.inventory"].barcode_add_cycle_count_quant(
                    inventory.id, product.id
                )

    def test_find_add_quant_wraps_access_errors(self):
        with patch.object(
            type(self.env["stock.quant"]),
            "check_access",
            side_effect=AccessError("denied"),
        ):
            with self.assertRaisesRegex(UserError, "unavailable"):
                self.env["stock.inventory"]._barcode_find_add_cycle_count_quant(
                    self.env["stock.quant"], [("id", "=", 1)]
                )

    def test_add_quant_rejects_invalid_identity(self):
        inventory_model = self.env["stock.inventory"]
        for inventory_id, product_id, lot_id in (
            (0, 1, False),
            (1, True, False),
            (1, 1, 0),
            (1, 1, True),
        ):
            with self.subTest(
                inventory_id=inventory_id,
                product_id=product_id,
                lot_id=lot_id,
            ):
                with self.assertRaisesRegex(UserError, "identity is invalid"):
                    inventory_model.barcode_add_cycle_count_quant(
                        inventory_id, product_id, lot_id
                    )

    def test_add_quant_rejects_invalid_product_target(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        inventory_model = self.env["stock.inventory"]
        service = self.env["product.product"].create(
            {"name": "Service add product", "type": "service"}
        )
        with self.assertRaisesRegex(UserError, "product is unavailable"):
            inventory_model.barcode_add_cycle_count_quant(inventory.id, service.id)

        product = self.env["product.product"].create(
            {"name": "Untracked add product", "is_storable": True}
        )
        lot = self.env["stock.lot"].create(
            {
                "name": "UNTRACKED-ADD-LOT",
                "product_id": product.id,
                "company_id": self.company.id,
            }
        )
        with self.assertRaisesRegex(UserError, "untracked product"):
            inventory_model.barcode_add_cycle_count_quant(
                inventory.id, product.id, lot_id=lot.id
            )

        corrupt = self.env["product.product"].create(
            {"name": "Corrupt tracking product", "is_storable": True}
        )
        # Tracking is a closed selection, so corrupt the stored value to reach
        # the defensive unsupported-tracking branch.
        self.env.cr.execute(
            "UPDATE product_template SET tracking = 'unsupported' WHERE id = %s",
            (corrupt.product_tmpl_id.id,),
        )
        corrupt.product_tmpl_id.invalidate_recordset(["tracking"])
        corrupt.invalidate_recordset(["tracking"])
        with self.assertRaisesRegex(UserError, "tracking is unsupported"):
            inventory_model.barcode_add_cycle_count_quant(inventory.id, corrupt.id)

    def test_add_quant_rejects_invalid_prefill(self):
        product = self.env["product.product"].create(
            {"name": "Invalid prefill product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        # The prefill is a closed selection, so corrupt the stored value to
        # reach the defensive invalid-prefill branch.
        self.env.cr.execute(
            "UPDATE stock_inventory SET prefill_counted_quantity = 'invalid' "
            "WHERE id = %s",
            (inventory.id,),
        )
        inventory.invalidate_recordset(["prefill_counted_quantity"])
        with self.assertRaisesRegex(UserError, "prefill is invalid"):
            self.env["stock.inventory"].barcode_add_cycle_count_quant(
                inventory.id, product.id
            )

    def test_add_quant_rejects_missing_line(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        other_product = self.env["product.product"].create(
            {"name": "Missing line product", "is_storable": True}
        )
        other_quant = self.make_unassociated_quant(count, other_product, quantity=1)
        with self.assertRaisesRegex(UserError, "no longer valid"):
            self.env["stock.inventory"]._barcode_get_add_cycle_count_quant_line(
                inventory, other_quant
            )

    def test_add_quant_rejects_quant_in_other_adjustment(self):
        product = self.env["product.product"].create(
            {"name": "Busy quant product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        other_inventory = self.env["stock.inventory"].create(
            {
                "name": "Other adjustment",
                "company_id": self.company.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 1,
                "current_inventory_id": other_inventory.id,
            }
        )
        with self.assertRaisesRegex(UserError, "already in an adjustment"):
            self.env["stock.inventory"].barcode_add_cycle_count_quant(
                inventory.id, product.id
            )

    def test_add_quant_rechecks_candidate_and_ownership(self):
        product = self.env["product.product"].create(
            {"name": "Race product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        quant = self.make_unassociated_quant(count, product, quantity=1)
        other_product = self.env["product.product"].create(
            {"name": "Other race product", "is_storable": True}
        )
        other_quant = self.make_unassociated_quant(count, other_product, quantity=1)

        with patch.object(
            type(self.env["stock.inventory"]),
            "_barcode_find_add_cycle_count_quant",
            side_effect=[quant, other_quant],
        ):
            with self.assertRaisesRegex(UserError, "no longer valid"):
                self.env["stock.inventory"].barcode_add_cycle_count_quant(
                    inventory.id, product.id
                )

        calls = {"count": 0}

        def find_and_claim(_model, _domain):
            calls["count"] += 1
            if calls["count"] == 2:
                quant.current_inventory_id = inventory.id
            return quant

        quant.current_inventory_id = False
        with patch.object(
            type(self.env["stock.inventory"]),
            "_barcode_find_add_cycle_count_quant",
            side_effect=find_and_claim,
        ):
            with self.assertRaisesRegex(UserError, "already in an adjustment"):
                self.env["stock.inventory"].barcode_add_cycle_count_quant(
                    inventory.id, product.id
                )

    def test_add_quant_rejects_linked_quant_from_other_inventory(self):
        product = self.env["product.product"].create(
            {"name": "Linked elsewhere product", "is_storable": True}
        )
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        other_inventory = self.env["stock.inventory"].create(
            {
                "name": "Elsewhere adjustment",
                "company_id": self.company.id,
                "location_ids": [(6, 0, [self.location.id])],
                "exclude_sublocation": True,
                "state": "in_progress",
            }
        )
        quant = self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.location.id,
                "company_id": self.company.id,
                "quantity": 1,
                "current_inventory_id": other_inventory.id,
            }
        )
        with patch.object(
            type(self.env["stock.inventory"]),
            "_barcode_validate_inventory",
            return_value=(inventory, count, quant),
        ):
            with self.assertRaisesRegex(UserError, "no longer valid"):
                self.env["stock.inventory"].barcode_add_cycle_count_quant(
                    inventory.id, product.id
                )

    def test_get_lines_rejects_invalid_quant(self):
        count = self.make_count(state="open")
        inventory, _quant = self.make_inventory(count)
        other_location = self.env["stock.location"].create(
            {
                "name": "Invalid line location",
                "usage": "internal",
                "company_id": self.company.id,
            }
        )
        invalid_quant = self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": other_location.id,
                "company_id": self.company.id,
                "quantity": 1,
                "current_inventory_id": inventory.id,
            }
        )
        inventory.stock_quant_ids = [(4, invalid_quant.id)]
        with self.assertRaisesRegex(UserError, "invalid lines"):
            self.env["stock.inventory"].barcode_get_cycle_count_lines(inventory.id)

    def test_save_line_rejects_missing_quant(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        payload = self.make_save_line(inventory, quant, 2.5)
        with patch.object(
            type(self.env["stock.inventory"]),
            "_barcode_validate_partial_count_payload",
            return_value=(999999, 2.5, False, False, payload["write_date"]),
        ):
            with self.assertRaisesRegex(UserError, "no longer valid"):
                self.env["stock.inventory"].barcode_save_cycle_count_line(
                    inventory.id, payload
                )

    def test_save_line_wraps_quant_access_errors(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        payload = self.make_save_line(inventory, quant, 2.5)
        with (
            patch.object(
                type(self.env["stock.inventory"]),
                "_barcode_resolve_partial_cycle_count",
                return_value=(inventory, count, quant),
            ),
            patch.object(
                type(self.env["stock.quant"]),
                "check_access",
                side_effect=AccessError("denied"),
            ),
        ):
            with self.assertRaisesRegex(UserError, "unavailable"):
                self.env["stock.inventory"].barcode_save_cycle_count_line(
                    inventory.id, payload
                )

    def test_save_line_rejects_stale_link_and_not_to_do(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        payload = self.make_save_line(inventory, quant, 2.5)

        def unlink_quant(quant_record):
            quant_record.current_inventory_id = False
            return self.env["stock.inventory"]._barcode_write_date_token(
                quant_record.write_date
            )

        with patch.object(
            type(self.env["stock.inventory"]),
            "_barcode_lock_partial_count_quant",
            side_effect=unlink_quant,
        ):
            with self.assertRaisesRegex(UserError, "no longer part of"):
                self.env["stock.inventory"].barcode_save_cycle_count_line(
                    inventory.id, payload
                )

        quant.current_inventory_id = inventory.id
        quant.to_do = False
        with self.assertRaisesRegex(UserError, "no longer valid"):
            self.env["stock.inventory"].barcode_save_cycle_count_line(
                inventory.id, payload
            )

    def test_validate_line_rejects_unlinked_invalid_and_bad_payload(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        other_product = self.env["product.product"].create(
            {"name": "Unlinked line product", "is_storable": True}
        )
        other_quant = self.make_unassociated_quant(count, other_product, quantity=1)
        with self.assertRaisesRegex(UserError, "no longer part of"):
            self.env["stock.inventory"]._barcode_validate_line(
                inventory, other_quant, 1
            )
        with self.assertRaisesRegex(UserError, "quantity is invalid"):
            self.env["stock.inventory"]._barcode_validate_line(
                inventory, quant, "not-a-number"
            )
        with self.assertRaisesRegex(UserError, "untracked line cannot contain"):
            self.env["stock.inventory"]._barcode_validate_line(
                inventory, quant, 1, lot_id=123, lot_name="LOT"
            )
        other_location = self.env["stock.location"].create(
            {
                "name": "Invalid line location",
                "usage": "internal",
                "company_id": self.company.id,
            }
        )
        quant.location_id = other_location.id
        with self.assertRaisesRegex(UserError, "no longer valid"):
            self.env["stock.inventory"]._barcode_validate_line(inventory, quant, 1)

    def test_completion_rejects_non_list_and_malformed_lines(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        with self.assertRaisesRegex(UserError, "must be a list"):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, "not-a-list"
            )
        with self.assertRaisesRegex(UserError, "must contain quant"):
            self.env["stock.inventory"].barcode_apply_cycle_count(
                inventory.id, [{"quant_id": quant.id}]
            )

    def test_close_rejects_differences(self):
        count = self.make_count(state="open")
        inventory, quant = self.make_inventory(count)
        with self.assertRaisesRegex(UserError, "Resolve all differences"):
            self.env["stock.inventory"].barcode_close_cycle_count(
                inventory.id,
                [self.make_line(quant, quant.quantity + 1)],
                confirm_zero=True,
            )
