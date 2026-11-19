{
    "name": "Barcode Stock Quality",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Run a reception's quality control inspections from the Barcode "
    "app, with photo evidence",
    "author": "Binhex, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/barcode-interface",
    "maintainers": ["szalatyzuzanna"],
    "license": "AGPL-3",
    "depends": [
        "barcode_stock",
        "quality_control_stock_oca",
    ],
    "assets": {
        "barcode_scanner.assets": [
            "barcode_stock_quality/static/src/**/*.esm.js",
            "barcode_stock_quality/static/src/**/*.xml",
            "barcode_stock_quality/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "barcode_stock_quality/static/tests/**/*",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
