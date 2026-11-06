``barcode_scanner`` is a framework and is not useful on its own: install a
feature module such as ``barcode_stock`` to get actual operations.

To build your own feature module, register your pieces into the framework
registries — no change to the base module is required.

Register a screen. Screens receive a ``navigate`` function and the route
``params`` (or what the optional ``props(params)`` entry returns); with Owl 3 a
component must declare the props it reads with ``useProps``:

```js
import {Component, useProps} from "@odoo/owl";
import {barcodeScreens} from "@barcode_scanner/js/registries.esm";

class MyScreen extends Component {
    static template = "my_module.MyScreen";
    props = useProps();
}

barcodeScreens.add("my_screen", {component: MyScreen});
```

Register a scan handler (tried in ``sequence`` order; the first that returns a
truthy value consumes the scan):

```js
import {barcodeScanHandlers} from "@barcode_scanner/js/registries.esm";

barcodeScanHandlers.add("my_handler", {
    async handle(barcode, parsed, {api, navigate, notify}) {
        // return true when handled
    },
}, {sequence: 50});
```

Register a home-screen tile. ``icon`` is a
[Material Symbols](https://fonts.google.com/icons) name, rendered as
``<i class="oi" data-icon="..."/>``:

```js
import {barcodeMenuTiles} from "@barcode_scanner/js/registries.esm";

barcodeMenuTiles.add("my_tile", {
    label: "My Screen",
    icon: "deployed_code",
    action: ({navigate}) => navigate("my_screen"),
}, {sequence: 50});
```

Register a barcode parser (tried in ``sequence`` order before the built-in
EAN13 one; return ``null`` to let the next parser try):

```js
import {barcodeParsers} from "@barcode_scanner/js/registries.esm";

barcodeParsers.add("my_symbology", (barcode) => {
    // return {type: "...", value: "<product code>", ...} or null
}, {sequence: 20});
```

Register a startup task, for data your module needs before the first scan
(``barcode_gs1`` reads its nomenclature this way). Tasks are awaited when the
app opens; one that fails is logged and skipped:

```js
import {barcodeStartupTasks} from "@barcode_scanner/js/registries.esm";

barcodeStartupTasks.add("my_config", (env) => loadMyConfig(env.services.orm));
```

Read scans in a screen with the ``useBarcodeHandler`` hook. The barcode service
counts the components that do (``readers.count``, reactive), so a scan source
such as a camera button can offer itself only while a screen reads scans:

```js
import {useBarcodeHandler} from "@barcode_scanner/js/hooks/use_barcode_handler.esm";

useBarcodeHandler({onScan: (barcode, parsed) => this.onScan(barcode, parsed)});
```

Call the server through the ``barcodeApi`` service (or the
``useBarcodeScanner`` hook): it wraps the ORM and shows the server's user-facing
error message to the operator. Grouped reads follow Odoo's
``formattedReadGroup(model, domain, groupby, aggregates, options)``:

```js
import {useBarcodeScanner} from "@barcode_scanner/js/hooks/use_inventory.esm";

const api = useBarcodeScanner();
const groups = await api.formattedReadGroup(
    "stock.quant",
    [["location_id", "=", locationId]],
    ["product_id"],
    ["quantity:sum"]
);
```
