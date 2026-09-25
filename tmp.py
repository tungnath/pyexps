import os

def run_exps():
    # This function processes the redirect logic. Testing redirection for now
    print("Running temp exps !!!")

    file_names = []
    # list files
    files = os.listdir("D:\\testdir")
    for f in files:
        print(f)
        file_names.append((f.split(".")[0]).split('_'))

    print(file_names)


    doc_file_names = []
    with open("D:\\names.txt", "r") as f:
        lines = f.readlines()
        for line in lines:
            print(line.strip())
            doc_file_names.append(line.strip().split(" "))

    print(doc_file_names)


    final_data = []
    new_data = set()
    for ab_it in file_names:
        for cd_it in doc_file_names:
            fg = list(set(ab_it) & set(cd_it))
            print(fg)
            if fg:
                final_data.append(("_".join(ab_it), cd_it))
            else:
                new_data.add("_".join(ab_it))

    # print(final_data)
    print(new_data)




if __name__ == "__main__":
    run_exps()
