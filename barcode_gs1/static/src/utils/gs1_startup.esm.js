import {barcodeStartupTasks} from "@barcode_scanner/registries.esm";
import {loadGs1Nomenclature} from "./gs1_nomenclature.esm";

/**
 * Read the GS1 nomenclature once, when the app starts, so the parser — which
 * runs synchronously on every scan — has the rules ready. The parser falls back
 * to its built-in identifiers if this never completes.
 */
barcodeStartupTasks.add("gs1_nomenclature", (env) =>
    loadGs1Nomenclature(env.services.orm, env.services.company?.currentCompany?.id)
);
