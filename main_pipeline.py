import os
import json
import csv
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from crewai import Agent, Task, Crew
from crewai.crews.crew_output import CrewOutput
from crewai_tools import SerperDevTool, SeleniumScrapingTool, FileReadTool
from tools.avatar_finder_tool import AvatarFinderTool
from tools.copy_reader_tool import CopyReaderTool
from tools.copy_writer_tool import CopyWriterTool
from tools.copy_saver_tool import CopySaverTool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import yaml
import argparse
from pydantic import create_model
import logging

# Load environment variables
load_dotenv()

class BaseCrew:
    OUTPUT_FOLDER = 'crew_io_files'

    def __init__(self):
        self.tool_mapping = {
            "search_tool": SerperDevTool(),
            "scraping_tool": SeleniumScrapingTool(),
            "file_read_tool": FileReadTool(),
            "avatar_finder_tool": AvatarFinderTool(),
            "copy_reader_tool": CopyReaderTool(),
            "copy_writer_tool": CopyWriterTool(),
            "copy_saver_tool": CopySaverTool(),
        }
        self.llm = ChatOpenAI(model='gpt-4-turbo', temperature=0)
        logging.basicConfig(level=logging.INFO)

    @staticmethod
    def load_yaml(file_path: str) -> Dict:
        with open(file_path, 'r') as file:
            return yaml.safe_load(file)

    def create_pydantic_models(self, model_configs):
        models = {}

        def create_model_recursive(model_config):
            fields = {}
            for name, type_ in model_config['fields'].items():
                try:
                    if isinstance(type_, dict):
                        nested_model = create_model_recursive({"name": name, "fields": type_})
                        fields[name] = (nested_model, ...)
                    elif type_.startswith("List[") and type_[5:-1] in models:
                        fields[name] = (List[models[type_[5:-1]]], ...)
                    elif type_ in models:
                        fields[name] = (models[type_], ...)
                    else:
                        fields[name] = (eval(type_), ...)
                except Exception as e:
                    logging.error(f"Error processing field {name} with type {type_}: {str(e)}")
                    raise

            return create_model(model_config['name'], **fields)

        for model_config in model_configs:
            try:
                models[model_config['name']] = create_model_recursive(model_config)
            except Exception as e:
                logging.error(f"Error creating model {model_config['name']}: {str(e)}")
                raise

        return models

    def create_agent(self, agent_config: Dict) -> Agent:
        tools = [self.tool_mapping[tool_name] for tool_name in agent_config.get('tools', [])]

        return Agent(
            role=agent_config['role'],
            goal=agent_config['goal'],
            backstory=agent_config['backstory'],
            verbose=True,
            allow_delegation=True,
            llm=self.llm,
            max_iterations=7,
            tools=tools
        )

    def create_task(self, task_config: Dict, agents: List[Agent], input_data: Dict, pydantic_models: Dict) -> Task:
        task_agent = next((agent for agent in agents if agent.role == task_config['agent']), agents[0])
        output_json = pydantic_models.get(task_config.get('output_json'))

        task_kwargs = {
            "name": task_config['name'],
            "description": task_config['description'].format(**input_data),
            "expected_output": task_config.get('expected_output', "A comprehensive analysis"),
            "output_json": output_json,
            "agent": task_agent,
            "human_input": False
        }

        if 'output_file' in task_config:
            task_kwargs["output_file"] = os.path.join(self.OUTPUT_FOLDER, task_config['output_file'])

        return Task(**task_kwargs)

    def run_crew(self, crew_config_path: str, **kwargs) -> Dict:
        """
        Runs a crew based on the given YAML configuration and any additional parameters.
        """
        try:
            config = self.load_yaml(crew_config_path)
            pydantic_models = self.create_pydantic_models(config.get('pydantic_models', []))
            agents = [self.create_agent(agent_config) for agent_config in config['agents']]

            tasks = []
            for task_config in config['tasks']:
                task = self.create_task(task_config, agents, kwargs, pydantic_models)
                tasks.append(task)

            crew = Crew(agents=agents, tasks=tasks, verbose=True)
            result = crew.kickoff()

            final_output = {}
            if isinstance(result, CrewOutput):
                for task in tasks:
                    task_result = task.output.raw if hasattr(task, 'output') else {}
                    if isinstance(task_result, str):
                        try:
                            task_result = json.loads(task_result)
                        except json.JSONDecodeError:
                            logging.warning(f"Failed to parse JSON for task {task.name}. Keeping as string.")
                    final_output[task.name] = task_result

                    output_file = getattr(task, 'output_file', None)
                    if output_file:
                        self.save_task_output(output_file, task_result, task.name)
                    else:
                        logging.info(f"No output file specified for task: {task.name}")
            else:
                final_output = {"unexpected_output": str(result)}

            return final_output

        except Exception as e:
            logging.error(f"Error running crew: {str(e)}")
            raise

    def save_task_output(self, file_path: str, data, task_name: str):
        """
        Save the output of a task to a specified file, handling CSV, JSON, or text.
        """
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            if file_path.endswith('.csv'):
                self.save_csv_file(file_path, data)
            elif file_path.endswith('.json'):
                self.save_json_file(file_path, data)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(str(data))

            logging.info(f"Saved output for task {task_name} to {file_path}")
        except Exception as e:
            logging.error(f"Error saving output for task {task_name} to {file_path}: {str(e)}")

    def save_csv_file(self, file_path: str, data):
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            if isinstance(data, str):
                f.write(data)
            elif isinstance(data, list):
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                for row in data:
                    writer.writerow(row)
            else:
                logging.warning(f"Unexpected data format for CSV file {file_path}. Saving as string.")
                f.write(str(data))

    def save_json_file(self, file_path: str, data: Dict):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

class CrewPipeline(BaseCrew):
    
    def create_detailed_persona(self, persona_number: int) -> Dict:
        """
        Creates a detailed persona for a given persona number.
        """
        result = self.run_crew("crew_config/detailed_persona.yml", persona_number=persona_number)
        if 'CreateDetailedPersona' in result and 'persona' in result['CreateDetailedPersona']:
            persona = result['CreateDetailedPersona']['persona']
            
            # Save individual persona file
            individual_file = os.path.join(self.OUTPUT_FOLDER, f'persona_{persona_number}.json')
            self.save_json_file(individual_file, {"persona": persona})
            logging.info(f"Saved persona {persona_number} to {individual_file}")
            
            return persona
        else:
            logging.warning(f"Expected structure not found in result for persona {persona_number}")
            return None

    def run_parallel_detailed_personas(self):
        """
        Creates detailed personas for 5 personas in parallel.
        """
        logging.info("Creating detailed personas in parallel...")
        all_personas = []
        with ThreadPoolExecutor() as executor:
            future_to_persona = {executor.submit(self.create_detailed_persona, i): i for i in range(1, 6)}
            for future in as_completed(future_to_persona):
                persona_number = future_to_persona[future]
                try:
                    persona = future.result()
                    if persona:
                        all_personas.append(persona)
                        logging.info(f"Detailed persona {persona_number} created successfully.")
                    else:
                        logging.warning(f"Failed to create persona {persona_number}.")
                except Exception as exc:
                    logging.error(f"Persona {persona_number} generated an exception: {exc}")

        # Save combined personas file
        combined_file = os.path.join(self.OUTPUT_FOLDER, 'all_personas.json')
        self.save_json_file(combined_file, {"personas": all_personas})
        logging.info(f"All personas generated and saved to {combined_file}")
        
        return all_personas

    def create_ad_copy_for_persona(self, persona_number: int) -> Dict:
        """
        Creates ad copy for a given persona number.
        """
        result = self.run_crew("crew_config/ad_copy.yml", persona_number=persona_number)
        logging.info(f"Ad copy for persona {persona_number} created successfully.")
        return result

    def run_parallel_ad_copy(self):
        """
        Creates ad copies for all personas in parallel.
        """
        logging.info("Creating ad copy for all personas in parallel...")
        all_ad_copies = {}
        with ThreadPoolExecutor() as executor:
            future_to_ad_copy = {executor.submit(self.create_ad_copy_for_persona, i): i for i in range(1, 6)}
            for future in as_completed(future_to_ad_copy):
                persona_number = future_to_ad_copy[future]
                try:
                    ad_copy = future.result()
                    all_ad_copies[f"persona_{persona_number}"] = ad_copy
                    logging.info(f"Ad copy for persona {persona_number} created successfully.")
                except Exception as exc:
                    logging.error(f"Ad copy for persona {persona_number} generated an exception: {exc}")

        return all_ad_copies

    def run_pipeline(self, job_url: str = None, mode: str = None):
        """
        Main pipeline function. Executes all stages if no mode is provided.
        :param job_url: URL to the job to be analyzed (only required for full mode)
        :param mode: Optional mode parameter to skip earlier steps ('personas', 'copy')
        """
        # Ensure job_url is provided when needed (default mode requires job_url)
        if mode is None and job_url is None:
            logging.error("job_url is required when running the full pipeline.")
            return {"error": "job_url is required for the full pipeline"}

        # Run the full pipeline
        if mode is None:
            logging.info("Running full pipeline...")

            # Run job_analysis and parallel crews
            job_analysis_result = self.run_crew('crew_config/job_analysis.yml', job_url=job_url)

            parallel_crews = ['brand_voice', 'candidate_demographics', 'competitor_analysis', 'employee_sentiment']

            logging.info("Running parallel crews...")
            with ThreadPoolExecutor() as executor:
                future_to_crew = {executor.submit(self.run_crew, f"crew_config/{crew_name}.yml", job_url=job_url): crew_name for crew_name in parallel_crews}
                for future in as_completed(future_to_crew):
                    crew_name = future_to_crew[future]
                    try:
                        result = future.result()
                        logging.info(f"{crew_name} Result: {json.dumps(result, indent=2)}")
                    except Exception as exc:
                        logging.error(f"{crew_name} generated an exception: {exc}")

            logging.info("Running `persona_outlines` crew...")
            persona_outlines_result = self.run_crew('crew_config/persona_outlines.yml', job_url=job_url)

            logging.info("Running parallel detailed personas creation...")
            detailed_personas = self.run_parallel_detailed_personas()

            logging.info("Running parallel ad copy creation for all personas...")
            ad_copies = self.run_parallel_ad_copy()

            final_result = {
                "job_analysis": job_analysis_result,
                "persona_outlines": persona_outlines_result,
                "detailed_personas": detailed_personas,
                "ad_copies": ad_copies
            }

            # Save the final combined output
            final_output_path = os.path.join(self.OUTPUT_FOLDER, "pipeline_output.json")
            try:
                with open(final_output_path, 'w') as f:
                    json.dump(final_result, f, indent=2, ensure_ascii=False)
                logging.info(f"Pipeline output saved to: {final_output_path}")
            except IOError as e:
                logging.error(f"Error writing pipeline output file: {str(e)}")
            return final_result

        # Mode: personas
        elif mode == "personas":
            logging.info("Running detailed persona creation (skipping earlier steps)...")
            detailed_personas = self.run_parallel_detailed_personas()

            logging.info("Running parallel ad copy creation for all personas...")
            ad_copies = self.run_parallel_ad_copy()

            final_result = {
                "detailed_personas": detailed_personas,
                "ad_copies": ad_copies
            }

        # Mode: copy
        elif mode == "copy":
            logging.info("Running ad copy creation (skipping earlier steps)...")
            ad_copies = self.run_parallel_ad_copy()

            final_result = {
                "ad_copies": ad_copies
            }

        else:
            logging.error(f"Invalid mode provided: {mode}")
            return {"error": "Invalid mode"}

        return final_result


def main():
    parser = argparse.ArgumentParser(description="Run the main pipeline with specific modes.")
    parser.add_argument("-m", "--mode", choices=["personas", "copy", "full"], default="full",
                        help="Mode to run the pipeline. Options: 'personas', 'copy', or 'full'. Default is 'full'.")
    parser.add_argument("-p", "--params", nargs="+", help="Additional parameters in the format key=value", default=[])

    args = parser.parse_args()

    # Convert params from key=value format into a dictionary
    params = dict(param.split('=') for param in args.params)

    crew = CrewPipeline()

    # Determine the mode
    mode = args.mode
    if mode == "personas":
        logging.info("Running in 'personas' mode...")
        crew.run_parallel_detailed_personas()
    elif mode == "copy":
        logging.info("Running in 'copy' mode...")
        crew.run_parallel_ad_copy()
    else:
        logging.info("Running the full pipeline...")
        job_url = params.get('job_url')
        crew.run_pipeline(job_url=job_url)


if __name__ == "__main__":
    main()
