import {BarcodeScannerState} from "@barcode_stock/js/services/barcode_scanner_state.esm";
import {patch} from "@web/core/utils/patch";

patch(BarcodeScannerState.prototype, {
    async _loadIsManually(records, model) {
        if (!records.length || records[0].is_manually !== undefined) {
            return;
        }
        try {
            const ids = records.map((record) => record.id);
            const extra = await this.orm.searchRead(
                model,
                [["id", "in", ids]],
                ["is_manually"]
            );
            const map = Object.fromEntries(
                extra.map((record) => [record.id, record.is_manually])
            );
            for (const record of records) {
                record.is_manually = map[record.id] || false;
            }
        } catch {
            // Ignore - fallback to main barcodes
        }
    },

    async preloadPicking() {
        const result = await super.preloadPicking(...arguments);
        await this._loadIsManually(this.moves, "stock.move");
        await this._loadIsManually(this.moveLines, "stock.move.line");
        const pickingTypeId = this.picking?.picking_type_id?.[0];
        if (pickingTypeId) {
            const [pickingType] = await this.orm.read(
                "stock.picking.type",
                [pickingTypeId],
                ["allow_insert_new_line"]
            );
            this.pickingTypeAllowInsertNewLine =
                pickingType?.allow_insert_new_line || false;
        } else {
            this.pickingTypeAllowInsertNewLine = false;
        }
        return result;
    },

    getSnapshot() {
        return {
            ...super.getSnapshot(...arguments),
            pickingTypeAllowInsertNewLine: this.pickingTypeAllowInsertNewLine || false,
        };
    },
});
