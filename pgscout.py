import logging
import sys
import time
import requests
from Queue import Queue
from threading import Thread

from flask import Flask, request, jsonify

from pgscout.ScoutGuard import ScoutGuard
from pgscout.ScoutJob import ScoutJob
from pgscout.cache import get_cached_encounter, cache_encounter, cleanup_cache
from pgscout.config import cfg_get, cfg_init
from pgscout.console import print_status
from pgscout.utils import get_pokemon_name, normalize_encounter_id, \
    normalize_spawn_point_id, load_pgpool_accounts, app_state
from werkzeug.exceptions import HTTPException

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(threadName)16s][%(module)14s][%(levelname)8s] %(message)s')

log = logging.getLogger(__name__)

# Silence some loggers
logging.getLogger('pgoapi').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)

scouts = []
jobs = Queue()

# ===========================================================================


@app.route("/iv", methods=['GET'])
def get_iv():
    if not app_state.accept_new_requests:
        return jsonify({
            'success': False,
            'error': 'Not accepting new requests.'
        })
        payload = {}
        payload['encounter_id'] = normalized['encounter_id']
	payload['pokemon_id'] = normalized['pokemon_id']
	payload['latitude'] = normalized['lat']
	payload['longitude'] = normalized['lon']
        payload['error'] = "PGSCOUT ONTVANGEN, PGSCOUT ACCEPTEERT GEEN NIEUWE REQUESTS"
	response = requests.post('http://192.168.1.101:1418/test6', json=payload)
    #return_iv(request.args)
    payload = {}	
    payload['encounter_id'] = request.args["encounter_id"]
    payload['pokemon_id'] = request.args["pokemon_id"]
    payload['latitude'] = request.args["latitude"]
    payload['longitude'] = request.args["longitude"]
    payload['pokehunt_id'] = request.args['pokehunt_id']
    #response = requests.post('http://192.168.1.101:1418/test3', json=payload)
    pokemon_id = request.args["pokemon_id"]
    pokemon_name = get_pokemon_name(pokemon_id)
    lat = request.args["latitude"]
    lng = request.args["longitude"]
    encounter_id = normalize_encounter_id(request.args.get("encounter_id"))
    spawn_point_id = normalize_spawn_point_id(request.args.get("spawn_point_id"))
    pokehunt_id = request.args["pokehunt_id"]

    # Check cache
    cache_key = encounter_id if encounter_id else "{}-{}-{}".format(pokemon_id, lat, lng)
    result = get_cached_encounter(cache_key)
    if result:
        log.info(
            u"Returning cached result: {:.1f}% level {} {} with {} CP".format(result['iv_percent'], result['level'], pokemon_name, result['cp']))
        response = requests.post(cfg_get('customwebhook'), json = job.result)
        if(response.status_code != 200):
            log.error("Error sending webhook: {}".format(response.raise_for_status()))
            return jsonify({
                'success': False,
                'error': 'Not accepting new requests.'
            })
        else:
            return jsonify({
                'success': True
            })

    # Create a ScoutJob
    job = ScoutJob(pokemon_id, encounter_id, spawn_point_id, lat, lng, pokehunt_id)
    jobs.put(job)

    # Enqueue and wait for job to be processed NO
    return jsonify({
        'success': True,
    })
    

@app.errorhandler(Exception)
def handle_http_exception(e):
	#requests.post('http://192.168.1.101:1418/test6', json=e)
	return "something went wrong", 400
	
	
def run_webserver():
    app.run(threaded=True, host=cfg_get('host'), port=cfg_get('port'))


def cache_cleanup_thread():
    while True:
        time.sleep(60)
        num_deleted = cleanup_cache()
        log.info("Cleaned up {} entries from encounter cache.".format(num_deleted))


def load_accounts(jobs):
    accounts_file = cfg_get('accounts_file')

    accounts = []
    if accounts_file:
        log.info("Loading accounts from file {}.".format(accounts_file))
        with open(accounts_file, 'r') as f:
            for num, line in enumerate(f, 1):
                fields = line.split(",")
                fields = map(str.strip, fields)
                accounts.append(ScoutGuard(fields[0], fields[1], fields[2], jobs))
    elif cfg_get('pgpool_url') and cfg_get('pgpool_system_id') and cfg_get('pgpool_num_accounts') > 0:

        acc_json = load_pgpool_accounts(cfg_get('pgpool_num_accounts'), reuse=True)
        if isinstance(acc_json, dict):
            acc_json = [acc_json]

        if len(acc_json) > 0:
            log.info("Loaded {} accounts from PGPool.".format(len(acc_json)))
            for acc in acc_json:
                accounts.append(ScoutGuard(acc['auth_service'], acc['username'], acc['password'], jobs))

    if len(accounts) == 0:
        log.error("Could not load any accounts. Nothing to do. Exiting.")
        sys.exit(1)

    return accounts


# ===========================================================================

log.info("PGScout starting up.")

cfg_init()

scouts = load_accounts(jobs)
for scout in scouts:
    t = Thread(target=scout.run)
    t.daemon = True
    t.start()

# Cleanup cache in background
t = Thread(target=cache_cleanup_thread, name="cache_cleaner")
t.daemon = True
t.start()

# Start thread to print current status and get user input.
t = Thread(target=print_status,
           name='status_printer', args=(scouts, 'logs', jobs))
t.daemon = True
t.start()

# Launch the webserver
t = Thread(target=run_webserver, name='webserver')
t.daemon = True
t.start()

# Dummy endless loop.
while True:
    time.sleep(1)
