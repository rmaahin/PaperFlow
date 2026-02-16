import os
import json
import arxiv
import shutil
import tarfile
import requests
from pathlib import Path
from datetime import datetime

ARXIV_RAW_PATH = "data/raw/arxiv"

class ArxivDownloader:
    def __init__(self, destination_path):
        self.destination_path = destination_path

    def fetch_metadata(self, arxiv_id):
        
        try:
            arxiv_search = arxiv.Search(id_list=[arxiv_id])
            client = arxiv.Client()
            results = client.results(arxiv_search)

            retrieved_paper = list(results)[0]
        
            return {
                "arxiv_id": arxiv_id,
                "title": retrieved_paper.title,
                "authors": [author.name for author in retrieved_paper.authors],
                "abstract": retrieved_paper.summary,
                "published": str(retrieved_paper.published),
                "categories": retrieved_paper.categories,
                "pdf_url": retrieved_paper.pdf_url
            }
        except Exception as e:
            print(f"There's no research paper with Arxiv ID: {arxiv_id}")
            return False

    def try_download_latex_source(self, arxiv_id):

        latex_source_urls = [f"https://arxiv.org/src/{arxiv_id}", f"https://arxiv.org/e-print/{arxiv_id}"]

        latex_filename = arxiv_id + ".tar.gz"
        latex_filepath = Path(ARXIV_RAW_PATH) / arxiv_id / latex_filename

        for url in latex_source_urls:
            try:
                response = requests.get(url, stream=True, timeout=30)
                if response.status_code == 200:
                    with open(latex_filepath, "wb") as f:
                        response.raw.decode_content = True
                        shutil.copyfileobj(response.raw, f)
                        print(f"Successfully saved {latex_filename}!")
                        return True
            except requests.RequestException as e:
                print(f"Failed to download from {url}: {e}")
                continue  

        print(f"Latex source code does not exist for {arxiv_id}.")
        return False
        
    def download_pdf(self, arxiv_id):
        pdf_source_url = f"https://arxiv.org/pdf/{arxiv_id}"

        pdf_filename = arxiv_id + ".pdf"
        pdf_filepath = Path(ARXIV_RAW_PATH) / arxiv_id / pdf_filename

        try:
            response = requests.get(pdf_source_url, stream=True, timeout=30)
            if response.status_code == 200:
                with open(pdf_filepath, "wb") as f:
                        response.raw.decode_content = True
                        shutil.copyfileobj(response.raw, f)
                        print(f"Successfully saved {pdf_filename}!")
                        return True
            else:
                print(f"PDF does not exist for {arxiv_id}.")
                return False
        except Exception as e:
            print(f"Failed to download PDF file for {arxiv_id}: {e}")
            return False
        
    def extract_latex(self, latex_tarpath, extract_dir):
        
        try:
            with tarfile.open(latex_tarpath, 'r:gz') as tar:
                tar.extractall(path=extract_dir)
            print(f"Extracted latex source file {latex_tarpath} to {extract_dir}")
            return True

        except Exception as e:
            print(f"Unexpected error occurred while extracting {latex_tarpath}: {e}")
            return False

    def download_paper(self, arxiv_id):

        # define the destination folder
        arxiv_folder = Path(self.destination_path) / arxiv_id
        
        # fetch metadata and save as a JSON
        metadata = self.fetch_metadata(arxiv_id=arxiv_id)

        if not metadata:
            metadata = {}
            return metadata, False
        
        arxiv_folder.mkdir(parents=True, exist_ok=True)

        latex_status = self.try_download_latex_source(arxiv_id=arxiv_id)

        metadata['has_latex'] = latex_status
        metadata['download_timestamp'] = str(datetime.now())

        if latex_status:
            latex_filename = arxiv_id + ".tar.gz"
            latex_filepath = Path(ARXIV_RAW_PATH) / arxiv_id / latex_filename
            extract_dir = Path(ARXIV_RAW_PATH) / arxiv_id / "latex_files"
            extract_status = self.extract_latex(latex_filepath, extract_dir)
            
            extract_path = Path(extract_dir)
            if extract_status and extract_path.exists() and any(extract_path.iterdir()):
                latex_filepath.unlink()  

        pdf_status = self.download_pdf(arxiv_id)

        if metadata.get('arxiv_id'):
            metadata_filename = arxiv_id + "_metadata.json"
            metadata_filepath = Path(ARXIV_RAW_PATH) / arxiv_id / metadata_filename
            with open(metadata_filepath, 'w') as metadata_file:
                json.dump(metadata, metadata_file, indent=4)

        if pdf_status or latex_status:
            overall_status = True
        else:
            overall_status = False

        return metadata, overall_status

if __name__=="__main__":
    
    arxiv_id = "1706.03762"
    downloader = ArxivDownloader(ARXIV_RAW_PATH)
    metadata, download_status = downloader.download_paper(arxiv_id)
    print(f"Download status: {download_status}")