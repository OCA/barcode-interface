import {Component, useState} from "@odoo/owl";
import {barcodeAppWidgets} from "@barcode_scanner/js/registries.esm";
import {useService} from "@web/core/utils/hooks";

export class DebugWidget extends Component {
    static template = "barcode_scanner.DebugWidget";
    static props = {};

    setup() {
        this.barcode = useService("barcodeScannerBarcode");
        this.readers = useState(this.barcode.readers);
        this.state = useState({open: false, input: ""});
    }

    get isVisible() {
        return Boolean(this.env.debug) && this.readers.count > 0;
    }

    toggle() {
        this.state.open = !this.state.open;
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.simulateScan();
        }
    }

    simulateScan() {
        const barcode = this.state.input.trim();
        if (!barcode) {
            return;
        }
        this.barcode.bus.trigger("barcode_scanned", {
            barcode,
            parsed: this.barcode.parseBarcode(barcode),
            source: "debug",
        });
    }
}

barcodeAppWidgets.add("debug_widget", {component: DebugWidget});
