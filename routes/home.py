import os
from datetime import datetime

from flask import Blueprint, redirect, render_template, send_from_directory, url_for

from db import fetch_all, fetch_one

home_bp = Blueprint('home_bp', __name__)


@home_bp.route('/')
def home():
    return redirect(url_for('home_bp.react_ui'))


@home_bp.route('/ui')
def react_ui():
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    return send_from_directory(static_dir, 'ui.html')
