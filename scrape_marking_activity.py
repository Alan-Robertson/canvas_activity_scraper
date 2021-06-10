import requests, json
import copy, sys, time
import datetime


api_key = None

# Change this for whatever your use case is
base_url = "https://canvas.sydney.edu.au/api/v1"


#########################################################
# Main Function
#########################################################

def main():

    if (len(sys.argv) < 2):
        print("Please provide a path to your canvas API key.")
        return

    global api_key # Poor Form
    key_path = sys.argv[1]
    api_key = open(key_path).read()[:-1]


    # Load Courses for User associated with API key
    print("Loading Courses...")
    courses=load_courses()


    # Present course menu
    print("Courses found:")
    index = menu(courses, lambda course: "\t{}\t-\t{}".format(course['id'], course['name']))
    course = courses[index]


    # Load staff from course to resolve IDs
    print("Finding Staff...")
    staff = get_staff(course['id'])
    staff = staff_by_id(staff)


    # Get all grading events from the course
    print("Finding Grading Events... [this may take a while for large courses]")
    events = get_grading_events(course['id'])


    # Print results to CSV
    print("Dumping to CSV...")
    csv_name = to_csv(course, events, staff)
    print("Written to {}".format(csv_name))

    return events, staff

#########################################################
# Pagination Progress Bar
#########################################################

class ProgressBar():
    ''' 
        This is a looping progress bar to indicate that things are happening
        When paginating large data sets
    '''
    def __init__(self, n_ticks=20):
        self.l_brace = '['
        self.r_brace = ']'
        self.puck = '<===>'
        self.blank = '-'
        self.curr_tick = 0
        self.n_ticks=n_ticks

        self.first_tick = True

        self.last_tick_str_len = 0 

        self.bar_len = len(self.l_brace) + len(self.r_brace) + len(self.puck) + len(self.blank) * self.n_ticks


    def tick(self):

        if not self.first_tick:
            sys.stdout.write("\b" * self.bar_len)
            sys.stdout.flush()
            self.last_tick_str_len = 0
        else:
            self.first_tick = False

        time.sleep(0.1)

        tick_str = "{}{}{}{}{}".format(
            self.l_brace,
            self.blank * self.curr_tick,
            self.puck ,
            self.blank * (self.n_ticks - self.curr_tick),
            self.r_brace)
        sys.stdout.write("{}".format(tick_str))

        sys.stdout.flush()
        self.curr_tick += 1
        self.curr_tick %= self.n_ticks

    def end(self):
        sys.stdout.write('\n')


#########################################################
# API Request Functions
#########################################################


def url_construct(terms, modifiers=None):
    '''
    url_construct
    Constructs an API request using some simple arguments
    : terms :     A dictionary containing terms and intermediate parameters
    : modifiers : Query Parameters

    Returns the constructed URL
    '''
    url = base_url

    # Unwrap the terms
    for q_string, val in terms.items():
        if val is not None:
            url += '/{}/{}'.format(q_string, val)
        else:
            url += '/{}'.format(q_string)


    url += '?'

    # Apply parameters, starting with the access token
    url += '{}={}'.format('access_token', api_key)

    if modifiers is not None:
        for q_string, val in modifiers.items():
            url += '&{}={}'.format(q_string, val)

    return url




def paginate_load(url):
    '''
        Iterates through a paginated load and exhausts all pages
        Could be done using a generator but I would like the data locally 
        May be highly inadvisable for very large datasets
    '''
    page_num = 1
    progress_bar = ProgressBar()
    
    token_url = lambda url: "{}&access_token={}".format(url, api_key)
    
    response = requests.get(url)

    entries = json.loads(response.text)

    print("Loading paginated results...")
    while 'next' in response.headers['link']:
        progress_bar.tick()

        urls = response.headers['link'].split(',')

        # Find the next url and Decapsulate from '< >'
        next_url = [i for i in urls if 'next' in i][0].split(';')[0][1:-1]

        page_num += 1
        url = token_url(next_url)

        response = requests.get(url)

        new_entries = json.loads(response.text)

        if not isinstance(entries, dict):
            # Easy lists
            entries += new_entries
        else:
            # For when we paginate dict objects like in the audit API calls
            for key in new_entries:

                # We could recursively unwrap dicts, but I don't want to?
                # This will drop links, we probably don't need them?
                if isinstance(entries[key], dict):
                    continue
                else:
                    if key in entries:
                        entries[key] += new_entries[key]
                    else:
                        entries[key] = new_entries[key]
    progress_bar.end()
    return entries


#########################################################
# API Query Functions
#########################################################


def load_courses():
    '''
        Load all courses that you are associated with as either a teacher, ta or designer
    '''
    ta_url = url_construct(
            {'courses': None},
            modifiers={
            'per_page'  :  '100',
            'enrollment_type' : 'ta'
            })

    teacher_url = url_construct(
            {'courses': None},
            modifiers={
            'per_page'  :  '100',
            'enrollment_type' : 'teacher'
            })

    designer_url = url_construct(
            {'courses': None},
            modifiers={
            'per_page'  :  '100',
            'enrollment_type' : 'designer'
            })

    courses = json.loads(requests.get(ta_url).text)
    courses += json.loads(requests.get(teacher_url).text)
    courses += json.loads(requests.get(designer_url).text)

    courses.sort(key=lambda x: x['name'])
    return courses

    

def get_grading_events(course_id):
    '''
        Load grading events associated with your course ID
    '''
    url = url_construct(
        { 'audit'        : None,
          'grade_change' : None
        },{ 
          'course_id'    : course_id,
          'per_page'     : '100'}
        )

    events = paginate_load(url)
    return events

def get_staff(course_id):
    staff = []

    # Get Teaching Assistants
    url = url_construct(
        {
            'courses'    : course_id,
            'users'      : None
        },{
            'enrollment_type[]':'ta',
            'per_page':'100'
        }
    )
    staff += json.loads(requests.get(url).text)

    # Get Lecturers
    url = url_construct(
        {
            'courses'    : course_id,
            'users'      : None
        },{
            'enrollment_type[]':'teacher',
            'per_page':'100'
        }
    )
    staff += json.loads(requests.get(url).text)

    # Get unit Designers
    url = url_construct(
        {
            'courses'    : course_id,
            'users'      : None
        },{
            'enrollment_type[]':'designer',
            'per_page':'100'
        }
    )
    staff += json.loads(requests.get(url).text)

    # Sort on ID
    staff.sort(key=lambda x: x['id'])
    return staff
#########################################################

# Display functions
breaking_line = "#####"
def menu(options, display_lambda):
    '''
        Lazy lambda menu
    '''
    print(breaking_line)
    for i, val in enumerate(options):
        print("[{}]\t{}".format(i, display_lambda(val)))

    target = None
    while target is None:
        print("Select an option")        
        try: # Poor error handling for input
            target = int(input("> ")) 
            if target < 0 or target > len(options):
                raise Exception()
        except:
            target = None
            print("Invalid option")
    print("\t".format(display_lambda(options[i])))
    return target


#########################################################

def staff_by_id(staff):
    '''
        Sort staff by ID for lazy lookups later
    '''
    id_staff = {}
    for staff_member in staff:
        id_staff[staff_member['id']] = staff_member

    return id_staff


def to_csv(course, events, staff):
    '''
        Prints the events to a readable CSV
    '''
    csv_name = "{}-{}.csv".format(course['name'], course['id'])
    with open(csv_name, 'w') as csv_file:

        for event in events['events']:

            # We're only looking at marking events here
            if event['event_type'] == 'grade_change':

                timestamp = event['created_at']
                date, time = timestamp.split('T')
                time = time[:-1] # Drop the Z at the end

                
                # Try to find the grader among the staff, sometimes this is listed as None
                try:
                    marker = staff[int(event['links']['grader'])]['id']
                except:
                   continue
                
                # Write to file
                csv_file.write('{},{},{},{}\n'.format(staff[marker]['name'], staff[marker]['id'], date, time))

    return csv_name

#########################################################
main()
