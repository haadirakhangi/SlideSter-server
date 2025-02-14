from flask import Flask, request, jsonify, session, json,send_file,make_response
from pymongo import MongoClient
import bcrypt
import jwt
from datetime import datetime, timedelta
import os
from bson import ObjectId
from dotenv import load_dotenv
from flask import request, jsonify
import openai
from openai import OpenAI
import re
import ast
from utils import *
import torch
import time
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from concurrent.futures import ThreadPoolExecutor
from werkzeug.utils import secure_filename
from tavily import TavilyClient
from zipfile import ZipFile
import shutil



load_dotenv()

app = Flask(__name__)
passw = os.getenv("passw")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
connection_string = f"mongodb+srv://hatim:{passw}@cluster0.f7or37n.mongodb.net/?retryWrites=true&w=majority"

slide_number = 3
tools = [
    {
        'type': 'function',
        'function':{
            'name': 'generate_information',
            'description': 'Generates information when given a topic and a slide number',
            'parameters': {
                'type': 'object',
                'properties': {
                    'topic': {
                        'type': 'string',
                        'description': 'The topic on which the information is to be generated. For Example: Introduction to Machine Learning'
                    },
                    'slide_number' :{
                        'type': 'string',
                        'description': 'The number of the slide at which the information is to be added.'
                    },
                    'n_points' :{
                        'type': 'string',
                        'description': 'The number of points of information to be generated, default is 5.'
                    }
                },
                'required': ['topic', 'slide_number', 'n_points']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'generate_image',
            'description': 'Generates images when given an image generation prompt',
            'parameters': {
                'type': 'object',
                'properties': {
                    'prompt': {
                        'type': 'string',
                        'description': 'An appropriate prompt for the image generation model following a specific format for example, Astronaut in a jungle, cold color palette, muted colors, detailed, 8k'
                    },
                    'slide_number' :{
                        'type': 'string',
                        'description': 'The number of the slide at which the generated image is to be added.'
                    },
                },
                'required': ['prompt', 'slide_number']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'change_style',
            'description': 'Change the style (color or font-size) of the text when given a color and font size',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text_color': {
                        'type': 'string',
                        'description': 'The color of transform the text into. Example red, green, etc.'
                    },
                    'font_size': {
                        'type': 'string',
                        'description': 'The size of the text.'
                    }
                },
                'required': ['text_color', 'font_size']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'generate_goals',
            'description': 'Generate recommendations for visualization (goals) to the user for exploring the given csv data. Helps to analyze the data. Use this when the user asks for recommendations from a csv file.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'n_goals': {
                        'type': 'number',
                        'description': 'The number of recommended visualizations or goals to generate. Default is 1.'
                    },
                    'persona': {
                        'type': 'string',
                        'description': 'Persona for who the goals or visualization recommendations are generated. Ex: a mechanic who wants to buy a car that is cheap but has good gas mileage'
                    }
                },
                'required': ['n_goals']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'generate_visualizations',
            'description': 'Use to generate visualization based on the user query',
            'parameters': {
                'type': 'object',
                'properties': {
                    'user_query': {
                        'type': 'string',
                        'description': 'The query to use to generate the visualization. Example: average price of cars by type, bar graph for gdp per capita and social support for the country Iceland'
                    },
                    'library': {
                        'type': 'string',
                        'description': 'The python library to use to generate the visualization. Can be one of the following libraries: seaborn, matplotlib, ggplot, plotly, bokeh, altair. Default is seaborn'
                    }
                },
                'required': ['user_query']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'edit_visualizations',
            'description': 'Use to edit a previously given visualization according to the user\'s instructions',
            'parameters': {
                'type': 'object',
                'properties': {
                    'instructions': {
                        'type': 'array',
                        'description': 'An array of string consisting of user instructions for refining the previous visualization.',
                        'items':{
                            'type': 'string',
                            'description': 'Instruction given by the user. Example: change the color of the chart to red.'
                        }
                    },
                    'library': {
                        'type': 'string',
                        'description': 'The python library to use to generate the visualization. Can be one of the following libraries: seaborn, matplotlib, ggplot, plotly, bokeh, altair. Default is seaborn'
                    }
                },
                'required': ['instructions']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'recommend_visualizations',
            'description': 'Use to recommend visualization based on the previously generated visualization. Use this when the user asks for visualizations which are similar to the previous visualization',
            'parameters': {
                'type': 'object',
                'properties': {
                    'n_recommendations': {
                        'type': 'number',
                        'description': 'The number of recommendations to generate given the previous visualization.'
                    },
                    'library': {
                        'type': 'string',
                        'description': 'The python library to use to generate the visualization. Can be one of the following libraries: seaborn, matplotlib, ggplot, plotly, bokeh, altair. Default is seaborn'
                    }
                },
                'required': ['n_recommendations']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'generate_question_bank',
            'description': 'Use to create a question bank on te given presentation',
            'parameters': {
                'type': 'object',
                'properties': {
                    'n_questions': {
                        'type': 'string',
                        'description': 'The number of questions in the question bank. Default is 10.'
                    },
                },
                'required': ['n_questions']
            }
        }
    },
    {
        'type': 'function',
        'function':{
            'name': 'generate_notes',
            'description': 'Use to create reference notes from presentation',
        }
    },
]

available_tools = {
    'generate_information': chat_generate_point_info,
    'generate_image': generate_image,
    'generate_goals': generate_goals,
    'generate_visualizations': generate_visualizations,
    'edit_visualizations': edit_visualizations,
    'recommend_visualizations': recommend_visualizations,
    'generate_notes': generate_notes,
    'generate_question_bank': generate_question_bank,
}
    

def MongoDB(collection_name):
    client = MongoClient(connection_string)
    db = client.get_database("SlideSter")
    records = db.get_collection(collection_name)
    return records


def generate_token(user_id):
    payload = {"user_id": user_id, "exp": datetime.utcnow() + timedelta(hours=1)}
    token = jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")
    return token


def create_session(user_email):
    session["user_email"] = user_email


# records = MongoDB('register')


@app.route("/adduser", methods=["POST"])
def adduser():
    new_record = request.json
    email = new_record["email"]
    existing_user = MongoDB('register').find_one({"email": email})
    if existing_user:
        response = {"message": "exists"}
        return jsonify(response)

    salt = bcrypt.gensalt()
    new_record["password"] = bcrypt.hashpw(new_record["password"].encode("utf-8"), salt)
    result = MongoDB('register').insert_one(new_record)

    if result.inserted_id:
        token = generate_token(str(result.inserted_id))
        response = {"message": "success", "token": token}
        return jsonify(response)
    else:
        response = {"message": "failed"}
        return jsonify(response)


@app.route("/home")
def home():
    return "hello"


@app.route("/profile", methods=["GET"])
def profile():
    user_email = session.get("user_email")
    response2 = MongoDB('register').find_one({"email": user_email})
    del response2["_id"]
    del response2["password"]
    return jsonify(response2)


@app.route("/login", methods=["POST"])
def login():
    new_record = request.json
    user = MongoDB('register').find_one({"email": new_record["email"]})
    if user:
        if bcrypt.checkpw(new_record["password"].encode("utf-8"), user["password"]):
            token = generate_token(str(user["_id"]))
            response = {"message": "success", "token": token}
            create_session(str(user["email"]))
            return jsonify(response)
        else:
            response = {"message": "password"}
            return jsonify(response)
    else:
        response = {"message": "username"}
        return jsonify(response)


@app.route("/model1", methods=["POST"])
def model1():
    data = request.json
    titles = data.get("titles")
    points = data.get("points")
    doc = data.get("doc")
    web = data.get("web")
    # print(titles)
    # print(points)
    print("Doc status:",doc)
    print("Web status:",web)
    ppt_data = {
      "titles": titles,
      "points": points,
      "doc" : doc,
      "web" : web
    }
    collection = MongoDB('ppt')
    result=collection.insert_one(ppt_data)
    session['info_id'] = str(result.inserted_id)
    response = {"message": True}
    return jsonify(response)


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    response = {"message": "success"}
    return jsonify(response)

@app.route("/suggest-titles", methods=["POST"])
def suggest_titles():
    # final_suggestion_list = [
    #     'Introduction', 'Applications', 'Types of Machine Learning',
    #     'Supervised Learning', 'Unsupervised Learning', 'Reinforcement Learning',
    #     'Data Preprocessing', 'Model Evaluation', 'Challenges and Limitations',
    #     'Future Trends'
    #     ]
    
    domain = request.form.get('domain')
    topic = request.form.get('topic')
    web = request.form.get('web')
    session['domain'] = domain
    session['topic'] = topic
    print("Web Status:",web)
    if 'file' not in request.files:
       if web=="true":
        print("Using Web Search")
        output = generate_slide_titles_from_web(topic)
        response_list = list(output.values())
        response = {"message": response_list,"doc":False}
        return jsonify(response)
        
       else: 
        print("Without Web Search")
        output = generate_slide_titles(topic)
        response_list = list(output.values())
        print(response_list)
        response = {"message": response_list,"doc":False}
        return jsonify(response)
    else:
        file = request.files['file']
        print("print file ",file)
        local_path = 'pdf-file'
        file.save(os.path.join(local_path, secure_filename(file.filename)))
        file_path = 'pdf-file/'+ secure_filename(file.filename)
        # embeddings = OpenAIEmbeddings()
        vectordb_file_path = ingest(file_path)
        vector_db= FAISS.load_local(vectordb_file_path, EMBEDDINGS, allow_dangerous_deserialization=True)
        query1 = topic
        query2 = "Technology or architecture"
        session["vectordb_file_path"]=vectordb_file_path
        docs1 = vector_db.similarity_search(query1)
        docs2 = vector_db.similarity_search(query2)
        all_docs = docs1 + docs2
        context = [doc.page_content for doc in all_docs]
        output = generate_slide_titles_from_document(topic, context)
        response_list = list(output.values())
        response = {"message": response_list,"doc":True}
        return jsonify(response)

@app.route('/generate-new-info', methods=['POST'])
def generate_new_info():
    data = request.get_json()
    topic = data.get('topic')
    main_topic = session['topic']
    information = generate_point_info(main_topic, topic=topic)
    print(information)
    keys = list(information.keys())
    return jsonify({"key": keys, "information": information})

@app.route("/generate-info")
def generate_info():
    print("Generating....")
    main_topic = session['topic']
    domain = session['domain']
    collection = MongoDB('ppt')
    doc_mongo = collection.find_one({'_id': ObjectId(session['info_id'])})
    topics = doc_mongo.get('titles')
    topics_split_one = topics[:int(len(topics)/2)]
    topics_split_two = topics[int(len(topics)/2):]
    num_points = doc_mongo.get('points')
    num_points_split_one = num_points[:int(len(num_points)/2)]
    num_points_split_two = num_points[int(len(num_points)/2):]

    # print("doc status",doc_mongo)
    doc = doc_mongo.get('doc')
    web = doc_mongo.get('web')
    print('Doc status:',doc_mongo)
    client = OpenAI(api_key=OPENAI_API_KEY1)
    assistant = client.beta.assistants.create(
        name="SLIDESTER",
        instructions="You are a helpful assistant for the Slidester presentation platform. Please use the functions provided to you appropriately to help the user.",
        model="gpt-3.5-turbo-0613",
        tools =  tools
    )
    thread = client.beta.threads.create()
    session['assistant_id'] = assistant.id
    session['thread_id'] = thread.id
    print('ASSITANT INITIALISED WITH ID: ',assistant.id)

    if not doc:
        if web:
            with ThreadPoolExecutor() as executor:
                print("Generating Content from web...")
                future_content_one = executor.submit(generate_point_info_from_web, main_topic,topics_split_one, num_points_split_one, 'first')
                future_content_two = executor.submit(generate_point_info_from_web, main_topic,topics_split_two, num_points_split_two, 'second')
                content_one = future_content_one.result()
                content_two = future_content_two.result()
                information = {}
                information.update(content_one)
                information.update(content_two)
                print(information)
                keys = list(information.keys())
                all_images = {}
                for topic in topics:
                    images = fetch_images_from_web(topic)
                    all_images[topic] = images
                return jsonify({"keys": keys, "information": information, "images": all_images, "domain": domain, "main_topic": main_topic})
        else:
            with ThreadPoolExecutor() as executor:
                # information = {
                # 'Introduction to Computer Vision': ['Computer vision is a field of study that focuses on enabling computers to see, recognize, and understand visual information.', 'It involves the use of various techniques such as image processing, pattern recognition, and machine learning algorithms.', 'Computer vision finds application in various domains including autonomous vehicles, robotics, healthcare, and surveillance systems.', 'Common tasks in computer vision include image classification, object detection, image segmentation, and image enhancement.', 'Python libraries like OpenCV and TensorFlow provide powerful tools and frameworks for implementing computer vision algorithms and applications.'],
                # 'The History of Computer Vision': ['The concept of computer vision dates back to the 1960s when researchers began exploring ways to enable computers to interpret visual information.', 'The development of computer vision was greatly influenced by advances in artificial intelligence and the availability of faster and more powerful hardware.', 'In the 1980s, computer vision techniques like edge detection and feature extraction gained popularity, leading to applications in fields like robotics and image recognition.', 'The 1990s saw significant progress in computer vision with the introduction of algorithms for object recognition, image segmentation, and motion detection.', 'In recent years, deep learning techniques, particularly convolutional neural networks(CNNs), have revolutionized computer vision by achieving state- of - the - art performance across a wide range of tasks.'],
                # }
                future_content_one = executor.submit(generate_point_info, main_topic, topics_split_one, num_points_split_one, 'first')
                future_content_two = executor.submit(generate_point_info, main_topic, topics_split_two, num_points_split_two, 'second')
                content_one = future_content_one.result()
                content_two = future_content_two.result()
                information = {}
                information.update(content_one)
                information.update(content_two)
                keys = list(information.keys())
                all_images = {}
                for topic in topics:
                    images = fetch_images_from_web(topic)
                    all_images[topic] = images
                print("information:----------",information)
                # print("Images:----------",all_images)
                # all_images = {'Introduction to Machine Learning': ['https://onpassive.com/blog/wp-content/uploads/2020/12/AI-01-12-2020-860X860-Kumar.jpg', 'https://www.flexsin.com/blog/wp-content/uploads/2019/05/1600_900_machine_learning.jpg', 'https://www.globaltechcouncil.org/wp-content/uploads/2021/06/Machine-Learning-Trends-That-Will-Transform-The-World-in-2021-1.jpg', 'http://csr.briskstar.com/Content/Blogs/ML Blog.jpg', 'https://s3.amazonaws.com/media.the-next-tech.com/wp-content/uploads/2021/01/19132558/Top-6-Machine-Learning-Trends-you-should-watch-in-2021.jpg'], 'Future Trends in Machine Learning': ['https://onpassive.com/blog/wp-content/uploads/2020/12/AI-01-12-2020-860X860-Kumar.jpg', 'https://tenoblog.com/wp-content/uploads/2019/03/Machine-Learning-Technologies.jpg', 'https://www.flexsin.com/blog/wp-content/uploads/2019/05/1600_900_machine_learning.jpg', 'https://tai-software.com/wp-content/uploads/2020/01/machine-learning.jpg', 'https://www.techolac.com/wp-content/uploads/2021/07/robot-1536x1024.jpg']}
                return jsonify({"keys": keys, "information": information, "images": all_images,"domain": domain, "main_topic": main_topic})
    else:
        with ThreadPoolExecutor() as executor:
            vectordb_file_path = session["vectordb_file_path"]
            vector_db = FAISS.load_local(vectordb_file_path, EMBEDDINGS, allow_dangerous_deserialization=True)
            topics_split_one_text = ', '.join(topics_split_one)
            topics_split_two_text = ', '.join(topics_split_two)
            rel_docs_one = vector_db.similarity_search(topics_split_one_text, k=10)
            rel_docs_two = vector_db.similarity_search(topics_split_two_text, k=10)
            context_one = [doc.page_content for doc in rel_docs_one]
            context_two = [doc.page_content for doc in rel_docs_two]
            future_content_one = executor.submit(generate_point_info_from_document, main_topic, topics_split_one, num_points_split_one, context_one, 'first')
            future_content_two = executor.submit(generate_point_info_from_document, main_topic, topics_split_two, num_points_split_two, context_two, 'second')
            content_one = future_content_one.result()
            content_two = future_content_two.result()
            information = {}
            information.update(content_one)
            information.update(content_two)
            print(information)
            keys = list(information.keys())
            all_images = {}
            for topic in topics:
                images = fetch_images_from_web(topic)
                all_images[topic] = images
            return jsonify({"keys": keys, "information": information, "images": all_images ,"domain": domain, "main_topic": main_topic})


def wait_on_run(run_id, thread_id):
    client = OpenAI(api_key=OPENAI_API_KEY1)
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id,
        )
        print('RUN STATUS', run.status)
        time.sleep(0.5)
        if run.status in ['failed', 'completed', 'requires_action']:
            return run

client = OpenAI(api_key = OPENAI_API_KEY1)
def get_tool_result(thread_id, run_id, tools_to_call, context):
    tools_outputs = []
    assistant_outputs = []
    all_tool_name = []
    for tool in tools_to_call:
        output = None
        tool_call_id = tool.id
        tool_name = tool.function.name
        tool_args = tool.function.arguments
        tool_to_call = available_tools.get(tool_name)
        print('TOOL CALLED:',tool_name)
        print('ARGUMENTS:', tool_args)
        all_tool_name.append(tool_name)
        if tool_name == 'generate_information':
            topic = json.loads(tool_args)['topic']
            n_points = ""
            if 'n_points' in json.loads(tool_args):
                n_points = json.loads(tool_args)['n_points']
            output = tool_to_call(topic= topic, n_points= n_points)
            print('OUTPUT:',output)
            if output:
                assistant_output = "Content has been Generated please accept it"
                assistant_outputs.append({'tool_call_id': tool_call_id, 'output': assistant_output})
                tools_outputs.append({'generate_info_output': output })
        elif tool_name == 'generate_image':
            prompt = json.loads(tool_args)['prompt']
            print('Generating image...')
            image_path = tool_to_call(prompt)
            print('Image generated and saved at path:',image_path)
            output = "Image has been Generated please accept it"
            assistant_outputs.append({'tool_call_id': tool_call_id, 'output': output})
            tools_outputs.append({'generate_image_output': image_path })
        elif tool_name == 'generate_goals':
            summary = session['summary']
            n_goals = 2
            if 'n_goals' in json.loads(tool_args):
                n_goals = json.loads(tool_args)['n_goals']
            persona = None
            if 'persona' in json.loads(tool_args):
                persona = json.loads(tool_args)['persona']
            goals = tool_to_call(summary,n_goals,persona)
            output = "Goals has been Generated please accept it"
            assistant_outputs.append({'tool_call_id': tool_call_id, 'output': output})
            tools_outputs.append({'generate_goal_output': goals })
        elif tool_name == 'generate_visualizations':
            summary = session['summary']
            goals = json.loads(tool_args)['user_query']
            library= 'seaborn'
            if 'library' in json.loads(tool_args):
                library = json.loads(tool_args)['library']
            visualization_image,visualization_chart = tool_to_call(summary, goals, library)
            image_path = "assistant_charts/chart1.png"
            session['charts_code'] = visualization_chart[0].code
            visualization_image.save(image_path)
            output = "Chart has been generated"
            assistant_outputs.append({'tool_call_id': tool_call_id, 'output': output})
            tools_outputs.append({'generate_visualizations_output': image_path })
        elif tool_name == 'edit_visualizations':
            summary = session['summary']
            code = session['charts_code']
            instructions = json.loads(tool_args)['instructions']
            library= 'seaborn'
            if 'library' in json.loads(tool_args):
                library = json.loads(tool_args)['library']
            edited_image,edited_chart = tool_to_call(summary, code, instructions, library)
            image_path = "assistant_charts/chart1.png"
            session['charts_code'] = edited_chart[0].code
            edited_image.save(image_path)
            output = "Chart has been edited"
            assistant_outputs.append({'tool_call_id': tool_call_id, 'output': output})
            tools_outputs.append({'edit_visualizations_output': image_path })
        elif tool_name == 'recommend_visualizations':
            summary = session['summary']
            code = session['charts_code']
            library= 'seaborn'
            n_recommendations = 1
            if 'n_recommendations' in json.loads(tool_args):
                n_recommendations = json.loads(tool_args)['n_recommendations']
            if 'library' in json.loads(tool_args):
                library = json.loads(tool_args)['library']
            recommended_images, recommended_chart = tool_to_call(summary, code, n_recc=n_recommendations, library=library)
            i = 1
            image_path_list = []
            for image in recommended_images:
                image_path = "assistant_charts/recommend/chart"+ str(i) +".png"
                image.save(image_path)
                image_path_list.append(image_path)
                i += 1
            session['charts_code'] = recommended_chart[0].code
            output = "Recommended Charts has been generated"
            assistant_outputs.append({'tool_call_id': tool_call_id, 'output': output})
            tools_outputs.append({'recommend_visualizations_output': image_path_list })
        elif tool_name=='generate_question_bank':
            n_questions = json.loads(tool_args)['n_questions']
            question_bank = tool_to_call(n_questions, context)
            output = "Question bank has been generated"
            tools_outputs.append({'generate_question_bank_output': question_bank })
            assistant_outputs.append({'tool_call_id': tool_call_id, 'output': output})
        elif tool_name=='generate_notes':
            presentation_notes = tool_to_call(context)
            output = "Presentation Notes has been generated"
            tools_outputs.append({'generate_notes_output': presentation_notes })
            assistant_outputs.append({'tool_call_id': tool_call_id, 'output': output})
        run=client.beta.threads.runs.submit_tool_outputs(thread_id=thread_id, run_id=run_id, tool_outputs=assistant_outputs)
    return tools_outputs,all_tool_name,run
        
@app.route('/chatbot-route', methods=['POST'])
def chatbot_route():
    data = request.get_json()
    print(data)
    tool = None
    query = data.get('userdata', '')
    headings = data.get('headings', '')
    bodies = data.get('bodies', '')
    main_topic = session['topic']
    result_string = ""

    # Iterate through the headings list starting from the second element (index 1) to the second-to-last element (index -1)
    for heading in headings[1:-1]:
        if heading in bodies:
            # Retrieve the corresponding list from the bodies dictionary
            body_list = bodies[heading]
            # Convert the list to a string and append the heading and its corresponding list values to the result string
            result_string += f"{heading}: {' '.join(map(str, body_list))}\n"
    print("my context",result_string)
    if query:         
        client = OpenAI(api_key=OPENAI_API_KEY1)
        assistant_id = session['assistant_id']
        print('ASSISTANT ID',assistant_id)
        thread_id = session['thread_id']
        print('THREAD ID', thread_id)
        
        message = client.beta.threads.messages.create(
            thread_id= thread_id,
            role="user",
            content= query,
        )
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=session['assistant_id'],
        )
        run = wait_on_run(run.id, thread_id)

        if run.status == 'failed':
            print(run.error)
        elif run.status == 'requires_action':
            all_output, tool, run = get_tool_result(thread_id, run.id, run.required_action.submit_tool_outputs.tool_calls,context=result_string)
            run = wait_on_run(run.id,thread_id)
        messages = client.beta.threads.messages.list(thread_id=thread_id,order="asc")
        content = None
        for thread_message in messages.data:
            content = thread_message.content
        if tool==None:
            chatbot_reply = content[0].text.value
            print("Chatbot reply-------------",chatbot_reply)
            response = {'chatbotResponse': chatbot_reply,'function_name': 'normal_chat'} 
            return jsonify(response)
        else:
            if "generate_information" in tool:
                print('Generating information')
                print(all_output[0]['generate_info_output'])
                chatbot_reply = "Yes sure! Your information has been added on your Current Slide!"
                keys = list(all_output[0]['generate_info_output'])
                all_images= {}
                images = fetch_images_from_web(keys[0])
                all_images[keys[0]] = images
                response = {'chatbotResponse': chatbot_reply, "images": all_images,'function_name': 'generate_information','key': keys, 'information': all_output[0]['generate_info_output']} 
                return jsonify(response)
            elif "generate_image" in tool:
                print('Generating Image')
                image_path = all_output[0]['generate_image_output']
                chatbot_reply = "Sure! I have generated your image and added it on your current slide. Let me know if there is anything else I can help you with!"
                # chatbot_reply = content[0].text.value
                image_url = f"/send_image/{image_path}"
                # Create a response object to include both image and JSON data
                response = {'chatbotResponse': chatbot_reply,'function_name': 'generate_image','image_url': image_path}
                return jsonify(response)
            elif "generate_goals" in tool:
                print('Generating Goals')
                goals = all_output[0]['generate_goal_output']
                print("Goal",goals)
                formatted_goals = []
                for goal in goals:
                    formatted_goal = f"Question: {goal.question}\nVisualization: {goal.visualization}\nExplanation: {goal.rationale}\n"
                    formatted_goals.append(formatted_goal)
                chatbot_reply = "\n".join(formatted_goals)
                # chatbot_reply =  ",".join([goal.visualization for goal in goals])
                # Create a response object to include both image and JSON data
                response = {'chatbotResponse': chatbot_reply,'function_name': 'generate_goals'}
                return jsonify(response)
            elif "generate_visualizations" in tool:
                print('Generating Charts')
                image_path = all_output[0]['generate_visualizations_output']
                chatbot_reply = content[0].text.value
                # Create a response object to include both image and JSON data
                response = {'chatbotResponse': chatbot_reply,'function_name': 'generate_image','image_url': image_path}
                return jsonify(response)
            elif "edit_visualizations" in tool:
                print('Editing Charts')
                image_path = all_output[0]['edit_visualizations_output']
                chatbot_reply = content[0].text.value
                # Create a response object to include both image and JSON data
                response = {'chatbotResponse': chatbot_reply,'function_name': 'generate_image','image_url': image_path}
                return jsonify(response)
            elif "recommend_visualizations" in tool:
                print('Recommending Charts')
                image_path_list = all_output[0]['recommend_visualizations_output']
                chatbot_reply = content[0].text.value
                # Create a response object to include both image and JSON data
                response = {'chatbotResponse': chatbot_reply,'function_name': 'generate_recommendations','image_url': image_path_list}
                return jsonify(response)
            elif "generate_question_bank" in tool:
                print('Generating Question Bank...')
                question_bank = all_output[0]['generate_question_bank_output']
                print("Question Bank:---------------------",question_bank)
                download_dir = os.path.join(os.getcwd(), "downloads")
                os.makedirs(download_dir, exist_ok=True)
                pdf_file_path = os.path.join(download_dir, f"{main_topic}_question_bank.pdf")
                generate_question_bank_pdf(pdf_file_path,main_topic,question_bank)
                chatbot_reply = "Question Bank has been generated and downloaded. Please verify it and let me know. Is there anything else I can help you with?"
                print("Chatbot reply-------------",chatbot_reply)
                response = {'chatbotResponse': chatbot_reply,'function_name': 'generate_question_bank', 'path': pdf_file_path} 
                return jsonify(response)
            elif 'generate_notes' in tool:
                print('Generating Notes...')
                notes = all_output[0]['generate_notes_output']
                print("Notes:------------------------",notes)
                download_dir = os.path.join(os.getcwd(), "downloads")
                os.makedirs(download_dir, exist_ok=True)
                pdf_file_path = os.path.join(download_dir, f"{main_topic}_question_bank.pdf")
                generate_notes_pdf(pdf_file_path,main_topic,notes)
                chatbot_reply = "Notes has been generated and downloaded. Please verify it and let me know. Is there anything else I can help you with?"
                print("Chatbot reply-------------",chatbot_reply)
                response = {'chatbotResponse': chatbot_reply,'function_name': 'generate_notes', 'path': pdf_file_path} 
                return jsonify(response)
            else:
                return jsonify({'error': 'User message not provided'}), 400

@app.route('/send_image', methods=['POST'])
def send_image():
    data = request.json
    image_path = data.get('image_path')
    return send_file(image_path, mimetype='image/png')


@app.route('/download_pdf', methods=['POST'])
def download_pdf():
    data = request.json
    pdf_path = data.get('pdf_path')
    return send_file(pdf_path, as_attachment=True)


@app.route('/send_images', methods=['POST'])
def send_images():
    data = request.json
    image_paths = data.get('image_path')
    temp_dir = 'temp_images'
    os.makedirs(temp_dir, exist_ok=True)

    # Copy images to the temporary directory
    for i, image_path in enumerate(image_paths):
        image_filename = f'image_{i}.png'  # Use a unique filename for each image
        image_destination = os.path.join(temp_dir, image_filename)
        shutil.copy(image_path, image_destination)

    # Create a zip file containing all the images
    zip_filename = 'images.zip'
    with ZipFile(zip_filename, 'w') as zip_file:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                zip_file.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), temp_dir))
    return send_file(zip_filename, as_attachment=True)

@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        filename = file.filename
        file_path = os.path.join('assistant_csv', filename)
        file.save(file_path)
        summary =  generate_summary(file_path)
        session['summary'] = summary
        print("Summary", summary)
        chatbot_reply = "Your csv file has been successfully uploaded. You can now use it to generate engaging and stunning visualizations of your data!"
        return jsonify({'message': 'File uploaded successfully','chatbotResponse': chatbot_reply ,'filename': filename}), 200
    else:
        return jsonify({'error': 'Upload failed'}), 500

if __name__ == "__main__":
  app.run(debug=True)