BUILD_FLAGS=-pthread -std=c++11 -pedantic -Wall -Wextra -Werror -fPIC $(CXXFLAGS) -DGENERATE_LIB
ASIO_FLAGS=-DASIO_STANDALONE -I./dependencies/asio-1.10.6/include
LIBS_FLAGS=-pthread $(LDLIBS)

DESTINATION=$(if ${DESTDIR}, ${DESTDIR}, /usr/)

all: build/librstats.so

build/rstats.o: ./src/rstats.cpp ./src/rstats.h ./src/syslog.h
	@mkdir -p build
	g++ $(CPPFLAGS) ${BUILD_FLAGS} ${ASIO_FLAGS} -c $< -o $@

build/librstats.so: ./build/rstats.o
	@mkdir -p build
	g++ -o $@ $< $(LDFLAGS) -shared ${LIBS_FLAGS}

install: all
	mkdir -p ${DESTINATION}/{lib,include}/
	cp build/librstats.so ${DESTINATION}/lib/
	cp src/rstats.h src/lib_export.h ${DESTINATION}/include/

clean:
	@rm -f build/*.o
	@rm -f build/*.so

uninstall:
	@rm -f ${DESTINATION}/lib/librstats.so
	@rm -f ${DESTINATION}/include/{rstats,lib_export}.h
