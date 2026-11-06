import "@barcode_scanner/js/api.esm";
import "@barcode_scanner/js/barcode.esm";
import "@barcode_scanner/js/router.esm";
import "@barcode_scanner/js/screens/main_screen.esm";
import "@barcode_scanner/js/store.esm";
import {Component, useProps, xml} from "@odoo/owl";
import {
    barcodeMenuTiles,
    barcodeScanHandlers,
    barcodeScreens,
    barcodeStartupTasks,
} from "@barcode_scanner/js/registries.esm";
import {
    contains,
    getService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import {describe, expect, test, waitFor} from "@odoo/hoot";
import {BarcodeScannerApp} from "@barcode_scanner/js/app.esm";
import {press} from "@odoo/hoot-dom";
import {useService} from "@web/core/utils/hooks";

const LOCATION_BARCODE = "9501101020917";
const EMPTY_LOCATION_BARCODE = "4006381333931";

class StockScreen extends Component {
    static template = xml`
        <div class="o-test-stock">
            <span class="o-test-location" t-out="this.props.params.location"/>
            <span class="o-test-qty" t-out="this.props.params.qty"/>
            <button class="o-test-back" t-on-click="() => this.router.goBack()">Back</button>
        </div>`;
    props = useProps();
    setup() {
        this.router = useService("barcodeRouter");
    }
}

/**
 * Type a code the way a keyboard-wedge scanner does: one key per character,
 * then Enter.
 */
async function scan(code) {
    for (const key of code) {
        await press(key);
    }
    await press("Enter");
}

describe("BarcodeScanner", () => {
    test("scanner app flow: home, scans, screen navigation and back", async () => {
        barcodeStartupTasks.add("test_startup", (env) =>
            expect.step(`startup ${Boolean(env.services.barcodeApi)}`)
        );
        barcodeScreens.add("test_stock", {component: StockScreen});
        barcodeMenuTiles.add("test_stock", {
            label: "Stock",
            icon: "inventory_2",
            action: ({navigate}) => navigate("test_stock", {location: "Manual"}),
        });
        // Mirrors a feature module: look up a scanned location, group its stock
        // and open a screen, or warn through the feedback service.
        barcodeScanHandlers.add("test_location", {
            async handle(barcode, parsed, {env, api, navigate}) {
                if (parsed?.type !== "ean13") {
                    return false;
                }
                const [group] = await api.formattedReadGroup(
                    "stock.quant",
                    [["location_id.barcode", "=", barcode]],
                    ["location_id"],
                    ["quantity:sum"]
                );
                if (!group) {
                    env.services.barcodeScannerFeedback.error({
                        notify: true,
                        message: "Location is empty",
                    });
                    return true;
                }
                navigate("test_stock", {
                    location: group.location_id[1],
                    qty: group["quantity:sum"],
                });
                return true;
            },
        });
        onRpc("stock.quant", "formatted_read_group", ({kwargs}) => {
            expect.step(`group ${kwargs.domain[0][2]}`);
            expect(kwargs).toMatchObject({
                groupby: ["location_id"],
                aggregates: ["quantity:sum"],
            });
            if (kwargs.domain[0][2] === EMPTY_LOCATION_BARCODE) {
                return [];
            }
            return [
                {
                    location_id: [8, "WH/Stock"],
                    "quantity:sum": 12,
                    __extra_domain: [["location_id", "=", 8]],
                },
            ];
        });

        await mountWithCleanup(BarcodeScannerApp);
        const barcode = getService("barcodeScannerBarcode");
        // No sound or vibration in the test browser.
        Object.assign(getService("barcodeScannerFeedback").enabled, {
            audio: false,
            vibration: false,
        });
        expect.verifySteps(["startup true"]);

        // Home screen: greeting (the test user's time zone is not a real one),
        // Material Symbols tile icon, and the home screen reads scans.
        expect(".ilx-home-title").toHaveText(/^Good (morning|afternoon|evening),/);
        expect(".ilx-home-grid-icon i.oi").toHaveAttribute("data-icon", "inventory_2");
        // The hidden capture input lives on <body>, outside the test fixture.
        expect(document.activeElement).toHaveClass("o-barcode-input");
        expect(barcode.readers.count).toBe(1);

        // No handler takes a non-EAN13 code.
        await scan("LOC-404");
        await waitFor(
            ".o_notification:has(.bg-warning):contains(Barcode not recognized)"
        );

        // An "error" feedback signal is shown as a danger notification.
        await scan(EMPTY_LOCATION_BARCODE);
        await waitFor(".o_notification:has(.bg-danger):contains(Location is empty)");
        expect(".ilx-home-screen").toHaveCount(1);

        // A known location opens the screen with the grouped stock.
        await scan(LOCATION_BARCODE);
        await waitFor(".o-test-stock");
        expect(".o-test-location").toHaveText("WH/Stock");
        expect(".o-test-qty").toHaveText("12");
        expect(".ilx-home-screen").toHaveCount(0);
        expect(barcode.readers.count).toBe(0);
        expect.verifySteps([
            `group ${EMPTY_LOCATION_BARCODE}`,
            `group ${LOCATION_BARCODE}`,
        ]);

        // Back returns to the home screen, which reads scans again.
        await contains(".o-test-back").click();
        await waitFor(".ilx-home-screen");
        expect(barcode.readers.count).toBe(1);

        // A tile opens its screen with its own params.
        await contains(".ilx-home-grid-item").click();
        await waitFor(".o-test-stock");
        expect(".o-test-location").toHaveText("Manual");
    });
});
