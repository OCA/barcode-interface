import {Component} from "@odoo/owl";
import {barcodeScreens} from "@barcode_scanner/js/registries.esm";
import {useService} from "@web/core/utils/hooks";

export class CycleCountDoneScreen extends Component {
    static props = ["params", "navigate?"];

    setup() {
        this.store = useService("barcodeStore");
    }

    backToList() {
        this.store.navigate(
            "cycle_count_list",
            {
                showAll: this.props.params.showAll,
            },
            {clearHistory: true}
        );
    }

    static template = "barcode_stock_cycle_count.CycleCountDoneScreen";
}

barcodeScreens.add("cycle_count_done", {component: CycleCountDoneScreen});
