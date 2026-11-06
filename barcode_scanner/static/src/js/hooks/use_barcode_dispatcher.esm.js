import {NotificationPlugin} from "@web/core/notifications/notification_plugin";
import {_t} from "@web/core/l10n/translation";
import {barcodeScanHandlers} from "@barcode_scanner/js/registries.esm";
import {useBarcodeHandler} from "@barcode_scanner/js/hooks/use_barcode_handler.esm";
import {useEnv} from "@web/owl2/utils";
import {usePlugin} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";

/**
 * Runs a scanned barcode through the registered scan handlers, in `sequence`
 * order, until one consumes it (returns a truthy value). If none do, notifies
 * that the barcode was not recognized.
 *
 * Handlers receive a context `{env, api, navigate, notify}` so feature modules
 * can add recognition logic without touching the home screen.
 */
export function useBarcodeDispatcher() {
    const env = useEnv();
    const api = useService("barcodeApi");
    const router = useService("barcodeRouter");
    const notification = usePlugin(NotificationPlugin);

    const notify = (message, options = {}) => notification.add(message, options);

    useBarcodeHandler({
        onScan: async (barcode, parsed) => {
            const ctx = {env, api, navigate: router.navigate.bind(router), notify};
            for (const handler of barcodeScanHandlers.getAll()) {
                if (await handler.handle(barcode, parsed, ctx)) {
                    return;
                }
            }
            notify(_t("Barcode not recognized"), {type: "warning"});
        },
    });
}
