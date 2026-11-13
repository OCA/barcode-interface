# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    is_manually = fields.Boolean(
        related="move_id.is_manually", store=False, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._barcode_scanner_sync_manual_move_quantity()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "quantity" in vals or "qty_picked" in vals:
            self._barcode_scanner_sync_manual_move_quantity()
        return res

    def _barcode_scanner_sync_manual_move_quantity(self):
        for line in self:
            move = line.move_id
            if not move.is_manually:
                continue
            total = sum(move.move_line_ids.mapped("quantity")) or sum(
                move.move_line_ids.mapped("qty_picked")
            )
            if total and move.product_uom_qty != total:
                move.product_uom_qty = total
