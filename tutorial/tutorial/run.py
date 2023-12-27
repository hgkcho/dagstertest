from tutorial import defs

if __name__ == "__main__":
    job = defs.get_job_def("hackernews_job")
    job.execute_in_process()
