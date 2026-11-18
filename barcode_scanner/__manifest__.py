{
    "name": "Barcode Scanner",
    "version": "18.0.1.0.1",
    "category": "Hidden",
    "summary": "Base scanning framework: client action, registries, scanner "
    "input and hooks",
    "author": "Binhex, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/barcode-interface",
    "maintainers": ["szalatyzuzanna"],
    "license": "AGPL-3",
    "depends": [
        "web",
    ],
    "data": [
        "views/action.xml",
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "barcode_scanner/static/src/assets_backend/*.esm.js",
        ],
        "barcode_scanner.assets": [
            "barcode_scanner/static/src/**/*.esm.js",
            "barcode_scanner/static/src/components/**/*.scss",
            "barcode_scanner/static/src/components/**/*.xml",
            ("remove", "barcode_scanner/static/src/assets_backend/*.esm.js"),
        ],
        "web.assets_unit_tests": [
            ("include", "barcode_scanner.assets"),
            "barcode_scanner/static/tests/**/*",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
