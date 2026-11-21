from ..services import drills
from ..utils.serialization import row
class DrillsController:
    list=staticmethod(drills.list_jobs)
    create=staticmethod(drills.create_job)
    start=staticmethod(drills.start_job)
    retry=staticmethod(drills.retry_job)
    @staticmethod
    def get(db,id):return row(drills.get_job(db,id))
    overlap=staticmethod(drills.overlap)
    research=staticmethod(drills.research_copy)
