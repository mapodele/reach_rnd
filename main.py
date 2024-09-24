import os
import json
import csv
from typing import Dict, List
from crewai import Agent, Task, Crew
from crewai.crews.crew_output import CrewOutput
from crewai_tools import SerperDevTool, SeleniumScrapingTool, FileReadTool, VisionTool
from tools.avatar_finder_tool import AvatarFinderTool
from tools.copy_saver_tool import CopySaverTool
from tools.copy_reader_tool import CopyReaderTool
from tools.copy_writer_tool import CopyWriterTool
from tools.price_estimator_tool import PriceEstimatorTool
from tools.image_download_tool import ImageDownloadTool
from tools.image_analysis_tool import ImageAnalysisTool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import yaml
import argparse
from pydantic import create_model
import logging

load_dotenv()

class BaseCrew:
    OUTPUT_FOLDER = 'crew_io_files'

    def __init__(self):
        self.tool_mapping = {
            "search_tool": SerperDevTool(),
            "scraping_tool": SeleniumScrapingTool(),
            "file_read_tool": FileReadTool(),
            "vision_tool": VisionTool(),
            "avatar_finder_tool": AvatarFinderTool(),
            "copy_saver_tool": CopySaverTool(),
            "copy_reader_tool": CopyReaderTool(),
            "copy_writer_tool": CopyWriterTool(),
            "price_estimator_tool": PriceEstimatorTool(),
            "image_download_tool": ImageDownloadTool(),
            "image_analysis_tool": ImageAnalysisTool()
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

    def create_detailed_persona(self, persona_number: int) -> Dict:
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

def main():
    parser = argparse.ArgumentParser(description="Run a specific crew configuration or persona generation.")
    parser.add_argument("crew_name", help="Name of the crew configuration to run (without .yml extension)")
    parser.add_argument("-p", "--params", nargs="+", help="Additional parameters in the format key=value", default=[])

    args = parser.parse_args()

    params = dict(param.split('=') for param in args.params)

    crew = BaseCrew()

    if args.crew_name == "detailed_persona":
        persona_number = int(params.get('persona_number', 1))
        print(f"Generating detailed persona {persona_number}...")
        persona = crew.create_detailed_persona(persona_number)
        if persona:
            print(f"Persona {persona_number} created successfully.")
        else:
            print(f"Failed to create persona {persona_number}.")

    elif args.crew_name == "detailed_personas":
        print("Generating all detailed personas...")
        all_personas = []
        for persona_number in range(1, 6):  # Generate 5 personas
            print(f"Generating detailed persona {persona_number}...")
            persona = crew.create_detailed_persona(persona_number)
            if persona:
                all_personas.append(persona)

        # Save combined personas file
        combined_file = os.path.join(crew.OUTPUT_FOLDER, 'all_personas.json')
        crew.save_json_file(combined_file, {"personas": all_personas})
        print(f"All personas generated and saved to {combined_file}")

    else:
        # Handle all crew configurations uniformly
        crew_config_path = os.path.join("crew_config", f"{args.crew_name}.yml")
        result = crew.run_crew(crew_config_path, **params)
        # print("\nCrew Execution Result:")
        # print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()