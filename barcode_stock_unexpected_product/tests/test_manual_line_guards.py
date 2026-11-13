# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestManualLineGuards(TransactionCase):
    """Defensive paths of the manual-line RPC and quantity synchronisation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.origin = cls.env.ref("stock.stock_location_stock")
        cls.destination = cls.env["stock.location"].create(
            {
                "name": "Manual guards destination",
                "usage": "internal",
                "location_id": cls.origin.location_id.id,
                "company_id": cls.company.id,
            }
        )
        cls.picking_type = cls.env.ref("stock.picking_type_internal")
        cls._allow_insert_new_line = cls.picking_type.allow_insert_new_line
        cls.picking_type.allow_insert_new_line = True

    @classmethod
    def tearDownClass(cls):
        cls.picking_type.write({"allow_insert_new_line": cls._allow_insert_new_line})
        super().tearDownClass()

    def _product(self, tracking="none"):
        return self.env["product.product"].create(
            {
                "name": f"Manual guard {tracking} product",
                "is_storable": True,
                "tracking": tracking,
            }
        )

    def _picking(self):
        return self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.origin.id,
                "location_dest_id": self.destination.id,
            }
        )

    def _manual_move(self, product, quantity=1):
        return self.env["stock.move"].create(
            {
                "name": product.display_name,
                "product_id": product.id,
                "product_uom_qty": quantity,
                "product_uom": product.uom_id.id,
                "picking_id": self._picking().id,
                "location_id": self.origin.id,
                "location_dest_id": self.destination.id,
                "company_id": self.company.id,
                "is_manually": True,
            }
        )

    def test_invalid_lot_id_is_rejected(self):
        product = self._product(tracking="lot")
        picking = self._picking()
        with self.assertRaises(UserError):
            self.env["stock.picking"].barcode_scanner_add_manual_line_to_picking(
                picking.id, product.id, 1, "not-a-number"
            )

    def test_missing_lot_is_rejected(self):
        product = self._product(tracking="lot")
        picking = self._picking()
        with self.assertRaises(UserError):
            self.env["stock.picking"].barcode_scanner_add_manual_line_to_picking(
                picking.id, product.id, 1, 999999999
            )

    def test_missing_picking_is_rejected(self):
        product = self._product()
        with self.assertRaises(UserError):
            self.env["stock.picking"].barcode_scanner_add_manual_line_to_picking(
                999999999, product.id, 1
            )

    def test_missing_product_is_rejected(self):
        picking = self._picking()
        with self.assertRaises(UserError):
            self.env["stock.picking"].barcode_scanner_add_manual_line_to_picking(
                picking.id, 999999999, 1
            )

    def test_lot_from_other_company_is_rejected(self):
        other_company = self.env["res.company"].create(
            {"name": "Manual guards other company"}
        )
        product = self._product(tracking="lot")
        lot = self.env["stock.lot"].create(
            {"name": "MANUAL-GUARD-OTHER-COMPANY", "product_id": product.id}
        )
        lot.company_id = other_company
        picking = self._picking()
        with self.assertRaises(UserError):
            self.env["stock.picking"].barcode_scanner_add_manual_line_to_picking(
                picking.id, product.id, 1, lot.id
            )

    def test_reservation_shortfall_is_rejected(self):
        product = self._product()
        self.env["stock.quant"]._update_available_quantity(product, self.origin, 5)
        picking = self._picking()
        move_model = type(self.env["stock.move"])
        with patch.object(move_model, "_update_reserved_quantity", return_value=0):
            with self.assertRaises(UserError):
                self.env["stock.picking"].barcode_scanner_add_manual_line_to_picking(
                    picking.id, product.id, 1
                )

    def test_delete_missing_move_is_rejected(self):
        with self.assertRaises(UserError):
            self.env["stock.picking"].barcode_scanner_delete_manual_line(999999999)

    def test_delete_completed_move_is_rejected(self):
        product = self._product()
        other_product = self._product(tracking="none")
        self.env["stock.quant"]._update_available_quantity(product, self.origin, 1)
        self.env["stock.quant"]._update_available_quantity(
            other_product, self.origin, 1
        )
        picking = self._picking()
        model = self.env["stock.picking"]
        result = model.barcode_scanner_add_manual_line_to_picking(
            picking.id, product.id, 1, auto_pick=True
        )
        model.barcode_scanner_add_manual_line_to_picking(
            picking.id, other_product.id, 1, auto_pick=True
        )
        move = self.env["stock.move"].browse(result["move_id"])
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE stock_move SET state = 'done' WHERE id = %s", [move.id]
        )
        move.invalidate_recordset(["state"])
        self.assertEqual(move.state, "done")
        self.assertNotIn(picking.state, ("done", "cancel"))
        with self.assertRaises(UserError):
            model.barcode_scanner_delete_manual_line(move.id)

    def test_delete_move_without_quantity_skips_unreserve(self):
        product = self._product()
        move = self._manual_move(product, quantity=0)
        result = self.env["stock.picking"].barcode_scanner_delete_manual_line(move.id)
        self.assertTrue(result["deleted"])
        self.assertEqual(result["move_id"], move.id)

    def test_create_line_syncs_manual_move_quantity(self):
        product = self._product()
        move = self._manual_move(product)
        regular_move = self._manual_move(product)
        regular_move.is_manually = False
        lines = (
            self.env["stock.move.line"]
            .with_context(move_line_pick_qty=True)
            .create(
                [
                    {
                        "move_id": move.id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "quantity": 1,
                        "location_id": self.origin.id,
                        "location_dest_id": self.destination.id,
                    },
                    {
                        "move_id": move.id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "quantity": 2,
                        "location_id": self.origin.id,
                        "location_dest_id": self.destination.id,
                    },
                    {
                        "move_id": regular_move.id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "quantity": 2,
                        "location_id": self.origin.id,
                        "location_dest_id": self.destination.id,
                    },
                ]
            )
        )
        self.assertEqual(move.product_uom_qty, 3)
        self.assertEqual(regular_move.product_uom_qty, 1)

        lines.write({"quantity": 4})
        self.assertEqual(move.product_uom_qty, 8)
        self.assertEqual(regular_move.product_uom_qty, 1)
