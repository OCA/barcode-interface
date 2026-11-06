import {Component, proxy, t, useProps, xml} from "@odoo/owl";
import {after, describe, expect, test} from "@odoo/hoot";
import {getService, mountWithCleanup} from "@web/../tests/web_test_helpers";
import {animationFrame} from "@odoo/hoot-dom";
import {useBarcode} from "@barcode_scanner/js/hooks/use_barcode.esm";

class Reader extends Component {
    static template = xml`<div class="o-reader"/>`;
    props = useProps({onScan: t.function()});
    setup() {
        useBarcode((ev) => this.props.onScan(ev.detail.barcode));
    }
}

class Screen extends Component {
    static template = xml`<Reader t-if="this.state.reading" onScan="this.props.onScan"/>`;
    static components = {Reader};
    props = useProps({onScan: t.function()});
    setup() {
        this.state = proxy({reading: true});
    }
}

describe("BarcodeScanner", () => {
    test("the components reading scans are counted while mounted", async () => {
        const scanned = [];
        const screen = await mountWithCleanup(Screen, {
            props: {onScan: (barcode) => scanned.push(barcode)},
        });
        const barcode = getService("barcodeScannerBarcode");
        after(() => barcode.destroy());
        expect(barcode.readers.count).toBe(1);
        barcode.bus.trigger("barcode_scanned", {barcode: "9501101020917"});
        expect(scanned).toEqual(["9501101020917"]);

        screen.state.reading = false;
        await animationFrame();
        expect(barcode.readers.count).toBe(0);
        barcode.bus.trigger("barcode_scanned", {barcode: "9501101020917"});
        expect(scanned.length).toBe(1);
    });
});
