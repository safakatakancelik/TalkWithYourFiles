# Revision 2 initialization prompt

The prompt below is saved exactly as it was written on 2026-11-12. It came with three sketches:
[sketch-1-layout-labeled.jpg](sketch-1-layout-labeled.jpg),
[sketch-2-layout-unlabeled.jpg](sketch-2-layout-unlabeled.jpg) and
[sketch-3-why-notes.jpg](sketch-3-why-notes.jpg).

---

these are some drafts outlining what I have in mind. 

for now I want you to build completely independent UI. we can use placeholder test data scenarios.

how user uses the app:
open the app. upload files. talk with an agent asking questions that files potentially have answers of.

there are two types of agents:

1. orchestrator agent
2. translator agent
3. chat agent


chat agent is the agent that talks with the user. in the photos, I used orchestrator agent's name for the chat agent as well, but the main chatbot screen at the bottom half of the screen is where the user interacts with a regular chat agent.
that bottom half of the screen can cover the entirety of the screen or collapse to half of the screen or collapse into a single row at the bottom. this can be happen by clicking the button at the center of the line that separates that chat section with the area above, the button has arrows on it.


each uploaded file, has one translator agent. translator agents represents the files. they know the content of the files, both real and have access to the embeddings (remember backend will be implemented in the future, currently we are focused on UI, I'm sharing additional context.) translator agents can cite the files, explain the contents of it, share a summary of it or do more, there will be more functionalities around this. however, essentially they represent the files and are able to talk conversationally.

orchestrator agent orchestrates the translator agents, triggers them by asking questions to either one, some or all of them, gathers information based on the user query, and returns the findings to the chat agent.


notice the circle with the dotted lines in the middle, that's the huddle area. when chat agent transmits the query of the user to the orchestrator agent, orchestrator agent sends out a message to all the translator agents (or maybe one, some or none of them based on the state and context, remember we are firstly building the UI). after the message is sent, translator agents who thinks they have relationship with the context and can be useful, they come to the huddle circle. however, the orchestrator agent also can call certain agents directly based on their own decisions or user's instructions. in the huddle area, agents discuss over the query with the orchestrator and each other. they try to come up to the solution, they give each other context and guidance. translators look into their files as much as needed. once things are settled, the orchestrator agent returns the findings to the chat agent, and the chat agent prepares the answer. everything is cited, nothing gets lost.


E button is opens an explorer. it lists all the files that are uploaded, and user uploads files here. this explorer has two tabular list views grouped by files and agents. initially each file has one agent, but in the future agents will be able to have 0 or more files associated with them.

S button opens a short table that lists sessions that user has, the latest on top.

C button opens a mind map, context map of the files, and shows files, entities they are linked to and this grows over time.



now I want you to do few things.

1. save the 3 screenshots I shared in docs/development/revision-2-initialization
2. save my current prompt there as it is
3. create a documentation that you will compose after discussing details with me by grilling me.
4. create a UI that I describe making sure this creates no backend dependencies.
5. enable a demo view with some test scenario that triggers all the agents to work with some dummy files, and we can keep this as a test case for future while keeping front end agnostic of the backend.



what do you say?  we can use react and typescript for front end i think.
