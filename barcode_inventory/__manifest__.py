{
    "name": "Barcode Inventory",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Inventory adjustments and stock counts by barcode, on top of "
    "stock_inventory",
    "author": "Binhex, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/barcode-interface",
    "maintainers": ["szalatyzuzanna"],
    "license": "AGPL-3",
    "depends": [
        "barcode_scanner",
        "stock_inventory",
    ],
    "assets": {
        "barcode_scanner.assets": [
            "barcode_inventory/static/src/**/*.scss",
            "barcode_inventory/static/src/**/*.esm.js",
            "barcode_inventory/static/src/**/*.xml",
        ],
        "web.assets_unit_tests": [
            "barcode_inventory/static/tests/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
