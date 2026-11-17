import "@barcode_stock_product_multi_barcode/js/product_multi_barcode.esm";
import {describe, expect, test} from "@odoo/hoot";
import {BarcodeScannerState} from "@barcode_stock/js/services/barcode_scanner_state.esm";

// A product with a main barcode and two alternates, on a move of a picking.
const PRODUCT = {id: 40, barcode: "2300001000008", display_name: "SunPaper 100"};
const ALTERNATES = [
    {id: 1, name: "2300001000009", product_id: [40, "SunPaper 100"]},
    {id: 2, name: "2300001000010", product_id: [40, "SunPaper 100"]},
];
const MOVE = {
    id: 100,
    product_id: [40, "SunPaper 100"],
    product_uom_qty: 10,
    quantity: 10,
    location_id: [8, "WH/Stock"],
    location_dest_id: [4, "Partners/Vendors"],
};

const PICKING = {
    id: 1,
    name: "WH/IN/00001",
    picking_type_id: [1, "Receipts"],
    location_id: [4, "Partners/Vendors"],
    location_dest_id: [8, "WH/Stock"],
    state: "assigned",
};

// A second picking holds another product, with an alternate of its own.
const PICKING_2 = {...PICKING, id: 2, name: "WH/IN/00002"};
const PRODUCT_2 = {id: 41, barcode: "2300002000003", display_name: "SunPaper 200"};
const ALTERNATES_2 = [{id: 3, name: "2300002000004", product_id: [41, "SunPaper 200"]}];
const MOVE_2 = {...MOVE, id: 101, product_id: [41, "SunPaper 200"]};

function stateWithAlternates() {
    const state = new BarcodeScannerState({});
    state.productsById = {40: PRODUCT};
    state.moves = [MOVE];
    state.packagings = [];
    state.alternateBarcodes = ALTERNATES;
    state.buildIndexes();
    return state;
}

describe("ProductMultiBarcode", () => {
    test("an alternate barcode resolves to the same move as the main one", () => {
        const state = stateWithAlternates();
        const main = state.getMoveCandidatesForBarcode(PRODUCT.barcode);
        const alt = state.getMoveCandidatesForBarcode(ALTERNATES[0].name);
        expect(alt.map((m) => m.id)).toEqual(main.map((m) => m.id));
        expect(alt[0].id).toBe(MOVE.id);
    });

    test("every alternate barcode maps to the product", () => {
        const state = stateWithAlternates();
        for (const alt of ALTERNATES) {
            const productId = state.indexes.barcodeToProductIds[alt.name]?.[0];
            expect(productId).toBe(PRODUCT.id);
        }
    });

    test("a barcode with no alternate still resolves through the main barcode", () => {
        const state = stateWithAlternates();
        expect(state.getMoveCandidatesForBarcode(PRODUCT.barcode)[0].id).toBe(MOVE.id);
    });

    test("an unknown barcode yields no candidates", () => {
        const state = stateWithAlternates();
        expect(state.getMoveCandidatesForBarcode("9999999999999")).toEqual([]);
    });

    test("preloadPicking loads and indexes the alternate barcodes", async () => {
        const orm = {
            searchRead(model) {
                if (model === "stock.picking") {
                    return [
                        {
                            id: 1,
                            name: "WH/IN/00001",
                            picking_type_id: [1, "Receipts"],
                            location_id: [4, "Partners/Vendors"],
                            location_dest_id: [8, "WH/Stock"],
                            state: "assigned",
                        },
                    ];
                }
                if (model === "stock.move") {
                    return [MOVE];
                }
                if (model === "stock.move.line") {
                    return [];
                }
                if (model === "product.packaging") {
                    return [];
                }
                if (model === "product.barcode") {
                    return ALTERNATES;
                }
                if (model === "stock.lot") {
                    return [];
                }
                return [];
            },
            read(model, ids) {
                if (model === "stock.picking.type") {
                    return [
                        {
                            id: 1,
                            code: "incoming",
                            use_existing_lots: false,
                            use_create_lots: true,
                        },
                    ];
                }
                if (model === "product.product") {
                    return ids.map((id) => ({...PRODUCT, id}));
                }
                return [];
            },
            // The preload asks stock.lot for its expiry fields; none here.
            call() {
                return {};
            },
        };
        const state = new BarcodeScannerState(orm);
        await state.preloadPicking(1);
        expect(state.alternateBarcodes).toHaveLength(2);
        expect(state.getMoveCandidatesForBarcode(ALTERNATES[0].name)[0].id).toBe(
            MOVE.id
        );
    });

    test("switching pickings does not leak the previous alternate barcodes", async () => {
        let barcodeSearches = 0;
        let resolveAlternates = null;
        let markAlternatesRequested = null;
        const alternatesRequested = new Promise((resolve) => {
            markAlternatesRequested = resolve;
        });
        const orm = {
            searchRead(model, domain) {
                if (model === "stock.picking") {
                    return [domain[0][2] === PICKING.id ? PICKING : PICKING_2];
                }
                if (model === "stock.move") {
                    return [domain[0][2] === PICKING.id ? MOVE : MOVE_2];
                }
                if (model === "product.barcode") {
                    if (barcodeSearches++ === 0) {
                        return ALTERNATES;
                    }
                    // Hold the second picking's alternates: the base preload
                    // has built the indexes and the patch waits on this call.
                    markAlternatesRequested();
                    return new Promise((resolve) => {
                        resolveAlternates = resolve;
                    });
                }
                return [];
            },
            read(model, ids) {
                if (model === "stock.picking.type") {
                    return [
                        {
                            id: 1,
                            code: "incoming",
                            use_existing_lots: false,
                            use_create_lots: true,
                        },
                    ];
                }
                if (model === "product.product") {
                    return ids.map((id) => (id === PRODUCT_2.id ? PRODUCT_2 : PRODUCT));
                }
                return [];
            },
            call() {
                return {};
            },
        };
        const state = new BarcodeScannerState(orm);
        await state.preloadPicking(PICKING.id);
        expect(state.getMoveCandidatesForBarcode(ALTERNATES[0].name)[0].id).toBe(
            MOVE.id
        );

        const switching = state.preloadPicking(PICKING_2.id);
        await alternatesRequested;
        // Snapshot the window before releasing the RPC: with the old ordering
        // the base build has already indexed picking 1's codes against product
        // 40, which picking 2 does not carry. Releasing the RPC first keeps a
        // failing assertion from leaving the preload pending.
        const leaked = {
            first: state.indexes.barcodeToProductIds[ALTERNATES[0].name],
            second: state.indexes.barcodeToProductIds[ALTERNATES[1].name],
        };
        resolveAlternates(ALTERNATES_2);
        await switching;

        expect(leaked.first).toBe(undefined);
        expect(leaked.second).toBe(undefined);
        expect(state.indexes.barcodeToProductIds[ALTERNATES_2[0].name]).toEqual([
            PRODUCT_2.id,
        ]);
        expect(state.getMoveCandidatesForBarcode(ALTERNATES_2[0].name)[0].id).toBe(
            MOVE_2.id
        );
        expect(state.indexes.barcodeToProductIds[ALTERNATES[0].name]).toBe(undefined);
    });
});
