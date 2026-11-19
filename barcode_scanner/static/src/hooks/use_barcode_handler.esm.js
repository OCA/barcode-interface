import {useBarcode} from "./use_barcode.esm";

export function useBarcodeHandler({onScan}) {
    useBarcode((ev) => {
        const payload = ev?.detail || {};
        if (onScan && payload.barcode) {
            onScan(payload.barcode, payload.parsed || null, payload);
        }
    });
}
