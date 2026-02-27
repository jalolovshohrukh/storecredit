from .home import home_bp
from .accounts import accounts_bp
from .transactions import txns_bp
from .budgets import budgets_bp
from .stats import stats_bp
from .recurring import recurring_bp
from .api import api_bp


def register_blueprints(app):
    app.register_blueprint(home_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(txns_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(recurring_bp)
    app.register_blueprint(api_bp)
