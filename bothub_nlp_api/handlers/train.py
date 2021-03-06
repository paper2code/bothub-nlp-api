import time
from bothub_nlp_celery.actions import ACTION_TRAIN, queue_name
from bothub_nlp_celery.app import celery_app
from bothub_nlp_celery.tasks import TASK_NLU_TRAIN_UPDATE
from bothub_nlp_celery.utils import ALGORITHM_TO_LANGUAGE_MODEL, choose_best_algorithm
from bothub_nlp_celery import settings as celery_settings

from .. import settings, utils
from ..utils import backend
from ..utils import get_repository_authorization

TRAIN_STATUS_TRAINED = "trained"
TRAIN_STATUS_PROCESSING = "processing"
TRAIN_STATUS_FAILED = "failed"


def train_handler(authorization, repository_version=None):
    repository_authorization = get_repository_authorization(authorization)

    languages_report = {}
    train_tasks = []

    for language in settings.SUPPORTED_LANGUAGES.keys():

        current_update = backend().request_backend_train(
            repository_authorization, language, repository_version
        )
        print(language)
        print(current_update)
        print('######')
        if not current_update.get("ready_for_train"):
            continue

        chosen_algorithm = current_update.get('algorithm')
        model = ALGORITHM_TO_LANGUAGE_MODEL[chosen_algorithm]

        if (model == 'SPACY' and language not in celery_settings.SPACY_LANGUAGES) or (
            model == 'BERT' and language not in celery_settings.BERT_LANGUAGES):
            model = None

        print(queue_name(current_update.get("language"), ACTION_TRAIN, model))
        if settings.BOTHUB_SERVICE_TRAIN == "celery":
            train_task = celery_app.send_task(
                TASK_NLU_TRAIN_UPDATE,
                args=[
                    current_update.get("current_version_id"),
                    current_update.get("repository_authorization_user_id"),
                    repository_authorization,
                ],
                queue=queue_name(
                    current_update.get("language"),
                    ACTION_TRAIN,
                    model),
            )
            train_tasks.append({"task": train_task, "language": language})
        elif settings.BOTHUB_SERVICE_TRAIN == "ai-platform":
            job_id = f'bothub_{settings.ENVIRONMENT}_train_{str(current_update.get("current_version_id"))}_{language}_{str(int(time.time()))}'
            utils.send_job_train_ai_platform(
                jobId=job_id,
                repository_version=str(current_update.get("current_version_id")),
                by_id=str(current_update.get("repository_authorization_user_id")),
                repository_authorization=str(repository_authorization),
                language=language,
                type_model=model
            )
            backend().request_backend_save_queue_id(
                update_id=str(current_update.get("current_version_id")),
                repository_authorization=str(repository_authorization),
                task_id=job_id,
                from_queue=0,
            )
        languages_report[language] = {"status": TRAIN_STATUS_PROCESSING}

    resp = {
        "SUPPORTED_LANGUAGES": list(settings.SUPPORTED_LANGUAGES.keys()),
        "languages_report": languages_report,
    }
    return resp
