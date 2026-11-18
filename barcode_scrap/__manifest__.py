{
    "name": "Barcode Scrap",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Scrap damaged or lost goods from the Barcode app",
    "author": "Binhex, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/barcode-interface",
    "maintainers": ["szalatyzuzanna"],
    "license": "AGPL-3",
    "depends": [
        "barcode_scanner",
        "stock",
    ],
    "assets": {
        "barcode_scanner.assets": [
            "barcode_scrap/static/src/**/*.esm.js",
            "barcode_scrap/static/src/**/*.xml",
            "barcode_scrap/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "barcode_scrap/static/tests/**/*",
        ],
    },
}
